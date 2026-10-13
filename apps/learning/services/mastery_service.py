from typing import Protocol
from django.conf import settings
from django.db import transaction
from django.contrib.auth import get_user_model
from apps.learning.models import LearningActivity, MasteryState, MasterySnapshot
from .bkt_service import BKTEstimator

STATUS_LEVELS = (
    (0, "BEGINNER", "初学", "#e35b65"),
    (30, "DEVELOPING", "发展中", "#ee9b41"),
    (50, "UNDERSTANDING", "理解", "#e7c957"),
    (70, "PROFICIENT", "熟练", "#36a6b7"),
    (85, "MASTERED", "掌握", "#46a879"),
)
RULE_DEFAULTS = {"coverage_weight": 0.35, "recent_weight": 0.40, "independence_weight": 0.15,
                 "difficulty_weight": 0.10, "recent_window": 8, "mastered_min_evidence": 5,
                 "mastered_min_distinct": 3, "single_problem_cap": 55.0, "insufficient_cap": 84.0}


class MasteryEstimator(Protocol):
    name: str
    def estimate(self, evidence: list[dict], available_problems: int, config: dict | None = None) -> tuple[float, dict]: ...


class RuleEstimator:
    name = "rule"

    def estimate(self, evidence, available_problems, config=None):
        c = {**RULE_DEFAULTS, **(config or {})}
        if not evidence:
            return 0.0, {"evidence_sufficient": False, "message": "尚无练习证据"}
        solved = {item["problem_id"] for item in evidence if item["correct"]}
        distinct = {item["problem_id"] for item in evidence}
        recent = evidence[-int(c["recent_window"]):]
        # More recent errors have greater influence; repeated attempts are evidence,
        # but do not increase coverage or diversity.
        weights = list(range(1, len(recent) + 1))
        recent_accuracy = sum(w * item["correct"] for w, item in zip(weights, recent)) / sum(weights)
        independence = sum(item["correct"] / (1 + item["hints_used"]) for item in recent) / len(recent)
        difficulty = sum((item["difficulty"] / 3) * item["correct"] for item in recent) / len(recent)
        coverage = len(solved) / max(available_problems, 1)
        index = 100 * (c["coverage_weight"] * coverage + c["recent_weight"] * recent_accuracy + c["independence_weight"] * independence + c["difficulty_weight"] * difficulty)
        sufficient = len(evidence) >= c["mastered_min_evidence"] and len(distinct) >= c["mastered_min_distinct"]
        if len(distinct) == 1:
            index = min(index, c["single_problem_cap"])
        elif not sufficient:
            index = min(index, c["insufficient_cap"])
        return round(max(0, min(100, index)), 2), {
            "kind": "规则掌握指数", "coverage": round(coverage, 4), "recent_accuracy": round(recent_accuracy, 4),
            "independence": round(independence, 4), "difficulty_score": round(difficulty, 4),
            "evidence_sufficient": sufficient, "message": "证据充足" if sufficient else "证据不足，继续尝试不同题目",
            "weights": {key: value for key, value in c.items()}, "formula": "100 × (0.35覆盖率 + 0.40近期加权正确率 + 0.15独立完成度 + 0.10难度表现)，再施加证据量上限",
        }


def get_estimator(name=None) -> MasteryEstimator:
    selected = name or getattr(settings, "MASTERY_ESTIMATOR", "rule")
    if selected == "bkt":
        return BKTEstimator()
    if selected == "rule":
        return RuleEstimator()
    raise ValueError("Unknown mastery estimator")


def mastery_label(index: float, evidence_count: int) -> dict:
    if evidence_count == 0:
        return {"status": "UNSEEN", "status_label": "未学习", "color": "#aeb9c8"}
    result = STATUS_LEVELS[0]
    for item in STATUS_LEVELS:
        if index >= item[0]:
            result = item
    return {"status": result[1], "status_label": result[2], "color": result[3]}


def serialize_mastery(state: MasteryState | None) -> dict:
    index = state.index if state else 0.0
    evidence = state.evidence_count if state else 0
    selected = getattr(settings, "MASTERY_ESTIMATOR", "rule")
    return {"index": round(index, 2), "bkt_probability": round(state.bkt_probability, 4) if state and evidence else None,
            "evidence_count": evidence, "distinct_problems": state.distinct_problems if state else 0,
            "explanation": state.explanation if state else {"message": "尚无学习证据", "evidence_sufficient": False},
            "selected_estimator": selected, "selected_estimate": (state.bkt_probability if state and evidence else None) if selected == "bkt" else index,
            **mastery_label(index, evidence)}


@transaction.atomic
def record_submission_evidence(submission) -> None:
    """Single writer, deduplicated submission events inside the judge transaction.

    The user row serializes updates across PostgreSQL-like stores; SQLite's
    BEGIN IMMEDIATE transaction mode serializes writers on this project's DB.
    """
    if not submission.is_valid:
        return
    get_user_model().objects.select_for_update().get(pk=submission.user_id)
    for point in submission.problem.knowledge_points.all():
        _, created = LearningActivity.objects.get_or_create(
            user_id=submission.user_id, knowledge_point=point, event_key=f"submission:{submission.pk}",
            defaults={"submission": submission, "correct": submission.status == "ACCEPTED", "hints_used": submission.hints_used,
                      "duration_seconds": submission.duration_seconds, "event_type": "submission"})
        if not created:
            continue
        state, _ = MasteryState.objects.select_for_update().get_or_create(user_id=submission.user_id, knowledge_point=point)
        activities = LearningActivity.objects.filter(user_id=submission.user_id, knowledge_point=point, correct__isnull=False, submission__isnull=False).select_related("submission__problem").order_by("created_at", "pk")
        evidence = [{"correct": event.correct, "problem_id": event.submission.problem_id,
                     "difficulty": event.submission.problem.difficulty, "hints_used": event.hints_used} for event in activities]
        available = point.problems.filter(is_active=True).count()
        state.index, rule_details = RuleEstimator().estimate(evidence, available, getattr(settings, "MASTERY_RULE_CONFIG", {}))
        state.bkt_probability, bkt_details = BKTEstimator().estimate(evidence, available, getattr(settings, "BKT_PARAMETERS", {}))
        state.evidence_count = len(evidence)
        state.distinct_problems = len({item["problem_id"] for item in evidence})
        state.explanation = {**rule_details, "bkt": bkt_details}
        state.save()
        MasterySnapshot.objects.create(user_id=submission.user_id, knowledge_point=point, submission=submission,
                                       index=state.index, bkt_probability=state.bkt_probability, evidence_count=state.evidence_count)
