from datetime import timedelta
from django.db.models import Count
from django.utils import timezone
from apps.problems.models import Submission
from apps.knowledge.models import KnowledgePoint
from apps.learning.models import MasteryState, MasterySnapshot, LearningActivity, MistakeRecord
from .mastery_service import serialize_mastery

VALID_STATUSES = [value for value in Submission.Status.values if value not in ("PENDING", "JUDGE_ERROR")]


def get_learning_summary(user, days=7):
    days = max(1, min(int(days), 366))
    now = timezone.localtime()
    beginning = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=days - 1)
    submissions = Submission.objects.filter(user=user, created_at__gte=beginning, status__in=VALID_STATUSES)
    total = submissions.count()
    accepted = submissions.filter(status="ACCEPTED").count()
    attempted = submissions.values("problem_id").distinct().count()
    solved = submissions.filter(status="ACCEPTED").values("problem_id").distinct().count()
    states = {state.knowledge_point_id: state for state in MasteryState.objects.filter(user=user)}
    mastery = [{"id": point.slug, "name": point.name, "chapter": point.chapter, **serialize_mastery(states.get(point.pk))} for point in KnowledgePoint.objects.all()]
    weak = sorted([point for point in mastery if point["evidence_count"] > 0 and point["index"] < 70], key=lambda point: (point["index"], point["id"]))
    daily = []
    # Local dates are important: timestamps are stored in UTC by Django.
    rows = list(submissions.values("created_at", "status"))
    for offset in range(days):
        date = (beginning + timedelta(days=offset)).date()
        on_day = [row for row in rows if timezone.localtime(row["created_at"]).date() == date]
        daily.append({"date": date.isoformat(), "submissions": len(on_day), "accepted": sum(row["status"] == "ACCEPTED" for row in on_day)})
    snapshots = MasterySnapshot.objects.filter(user=user, created_at__gte=beginning).select_related("knowledge_point").order_by("created_at")
    changes = {}
    for snapshot in snapshots:
        slug = snapshot.knowledge_point.slug
        if slug not in changes:
            previous = MasterySnapshot.objects.filter(user=user, knowledge_point=snapshot.knowledge_point, created_at__lt=beginning).order_by("-created_at", "-pk").first()
            changes[slug] = {"id": slug, "name": snapshot.knowledge_point.name, "before": previous.index if previous else 0, "after": snapshot.index}
        else:
            changes[slug]["after"] = snapshot.index
    for change in changes.values():
        change["difference"] = round(change["after"] - change["before"], 2)
    return {"period_days": days, "period_start": beginning.isoformat(), "period_end": now.isoformat(),
        "total_submissions": total, "accepted_submissions": accepted, "attempted_problems": attempted, "solved_problems": solved,
        "submission_accuracy": round(accepted / total * 100, 2) if total else None,
        "problem_pass_rate": round(solved / attempted * 100, 2) if attempted else None,
        "accuracy": round(accepted / total * 100, 2) if total else None,
        "excluded_infrastructure_submissions": Submission.objects.filter(user=user, created_at__gte=beginning, status="JUDGE_ERROR").count(),
        "knowledge_mastery": mastery, "weak_points": weak, "daily_trend": daily,
        "mistake_types": list(MistakeRecord.objects.filter(user=user, created_at__gte=beginning).values("error_type").annotate(count=Count("pk")).order_by("error_type")),
        "mastery_changes": list(changes.values()),
        "learned_points": sum(point["evidence_count"] > 0 for point in mastery),
        "mastered_points": sum(point["status"] == "MASTERED" for point in mastery),
        "knowledge_coverage": round(sum(point["evidence_count"] > 0 for point in mastery) / len(mastery) * 100, 2) if mastery else 0,
        "average_mastery": round(sum(point["index"] for point in mastery) / len(mastery), 2) if mastery else 0}
