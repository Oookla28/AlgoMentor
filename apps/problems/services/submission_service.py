from datetime import timedelta
import uuid
from django.conf import settings
from django.db import transaction
from django.contrib.auth import get_user_model
from django.utils import timezone
from core.exceptions import CodeExecutionError, ValidationError
from core.execution.provider import get_execution_provider, validate_program, ExecutionLimits
from apps.problems.models import Problem, Submission, TestResult, ExecutionRequest
from .judge_service import judge_problem


@transaction.atomic
def reserve_execution(user, kind):
    get_user_model().objects.select_for_update().get(pk=user.pk)
    count = ExecutionRequest.objects.filter(user=user, created_at__gte=timezone.now() - timedelta(minutes=1)).count()
    if count >= getattr(settings, "EXECUTION_REQUESTS_PER_MINUTE", 8):
        raise CodeExecutionError("每分钟执行次数已达到上限，请稍后重试。", code="EXECUTION_RATE_LIMITED", status_code=429)
    ExecutionRequest.objects.create(user=user, kind=kind)


def run_code(user, code, stdin="", provider=None):
    if not isinstance(stdin, str):
        raise ValidationError("标准输入必须为字符串。")
    validate_program(code, stdin, ExecutionLimits())
    reserve_execution(user, "run")
    return (provider or get_execution_provider()).run(code, stdin, ExecutionLimits())


def submit_code(user, problem_id, code, hints_used=0, duration_seconds=0, request_key=None, provider=None):
    validate_program(code, "", ExecutionLimits())
    try:
        hints_used, duration_seconds = int(hints_used), float(duration_seconds)
    except (TypeError, ValueError) as exc:
        raise ValidationError("提示次数与答题时长必须为数字。") from exc
    import math
    if not 0 <= hints_used <= 50 or not math.isfinite(duration_seconds) or not 0 <= duration_seconds <= 86400:
        raise ValidationError("提示次数或答题时长超出范围。")
    try:
        problem_id = int(problem_id)
    except (TypeError, ValueError) as exc:
        raise ValidationError("题目编号必须为整数。") from exc
    key = request_key or uuid.uuid4().hex
    if not isinstance(key, str) or len(key) > 64:
        raise ValidationError("请求标识必须为长度不超过 64 的字符串。")
    problem = Problem.objects.get(pk=problem_id, is_active=True)
    hints_used = max(hints_used, authentic_hint_count(user, problem))
    with transaction.atomic():
        get_user_model().objects.select_for_update().get(pk=user.pk)
        existing = Submission.objects.filter(user=user, request_key=key).first()
        if existing:
            expire_pending_submission(existing)
            if existing.problem_id != problem.id or existing.code != code:
                raise ValidationError("该请求标识已经用于其他提交。", code="IDEMPOTENCY_CONFLICT")
            return existing
        reserve_execution(user, "submit")
        submission = Submission.objects.create(user=user, problem=problem, code=code, hints_used=hints_used,
                                               duration_seconds=duration_seconds, request_key=key)
    # Remote HTTP happens after the persisted request and outside DB locks.
    try:
        outcome = judge_problem(problem, code, provider or get_execution_provider())
    except Exception as exc:
        import logging
        if not isinstance(exc, CodeExecutionError):
            logging.getLogger("algomentor").error("judge provider failed submission=%s exception_type=%s", submission.pk, type(exc).__name__)
        message = exc.message if isinstance(exc, CodeExecutionError) else "隔离执行服务返回异常；本次不计入成绩。"
        with transaction.atomic():
            submission = Submission.objects.select_for_update().get(pk=submission.pk)
            submission.status = "JUDGE_ERROR"
            submission.error_message = message
            submission.finished_at = timezone.now()
            submission.total_cases = problem.test_cases.count()
            submission.save()
        return submission
    with transaction.atomic():
        submission = Submission.objects.select_for_update().get(pk=submission.pk)
        if submission.status != "PENDING":
            return submission
        submission.status = outcome.status
        submission.finished_at = timezone.now()
        submission.passed_cases, submission.total_cases = outcome.passed_cases, outcome.total_cases
        submission.elapsed_seconds = sum(case.execution.elapsed_seconds for case in outcome.outcomes)
        submission.save()
        TestResult.objects.bulk_create([TestResult(submission=submission, test_case=case.case, status=case.status,
              stdout=case.execution.stdout, stderr=case.execution.stderr, elapsed_seconds=case.execution.elapsed_seconds,
              memory_kb=case.execution.memory_kb, provider=case.execution.provider) for case in outcome.outcomes])
        from apps.learning.services.mastery_service import record_submission_evidence
        from apps.learning.services.mistake_service import update_mistakes
        record_submission_evidence(submission)
        update_mistakes(submission)
    return submission


def serialize_submission(submission):
    expire_pending_submission(submission)
    from .diagnosis_service import diagnose_submission
    results = []
    for result in submission.test_results.select_related("test_case"):
        public = {"sequence": result.test_case.sequence, "hidden": result.test_case.is_hidden,
                  "status": result.status, "elapsed_seconds": result.elapsed_seconds, "memory_kb": result.memory_kb}
        if not result.test_case.is_hidden:
            public.update({"stdin": result.test_case.stdin, "expected_output": result.test_case.expected_output,
                           "stdout": result.stdout, "stderr": result.stderr})
        results.append(public)
    completed = submission.is_valid
    return {"id": submission.pk, "problem_id": submission.problem_id, "status": submission.status,
            "status_label": "评测未完成" if submission.status == "JUDGE_ERROR" else submission.get_status_display(),
            "evaluation_completed": completed,
            "passed_cases": submission.passed_cases if completed else None, "total_cases": submission.total_cases,
            "elapsed_seconds": submission.elapsed_seconds if completed else None, "error_message": submission.error_message,
            "is_valid": submission.is_valid, "test_results": results, "diagnosis": diagnose_submission(submission),
            "created_at": submission.created_at.isoformat()}


def authentic_hint_count(user, problem):
    """Saved teaching evidence is a lower bound; client self-reports only add.

    Hint history predating the most recent independent acceptance is excluded.
    Untimestamped legacy hints are conservatively counted.
    """
    from apps.tutor.models import TeachingSession
    from django.utils.dateparse import parse_datetime
    previous = Submission.objects.filter(user=user, problem=problem, status="ACCEPTED").order_by("-created_at").first()
    count = 0
    for teaching in TeachingSession.objects.filter(user=user, problem=problem):
        for hint in teaching.provided_hints:
            moment = None
            try:
                moment = parse_datetime(hint.get("at", "")) if isinstance(hint, dict) else None
            except (ValueError, TypeError):
                pass
            if moment is not None and timezone.is_naive(moment):
                moment = timezone.make_aware(moment)
            if previous is None or moment is None or moment > previous.created_at:
                count += 1
    from apps.learning.models import LearningActivity
    delivered = LearningActivity.objects.filter(user=user, submission__problem=problem, event_type="hint")
    if previous:
        delivered = delivered.filter(created_at__gt=previous.created_at)
    count += delivered.values("event_key").distinct().count()
    return min(count, 50)


def expire_pending_submission(submission):
    """Recover from interrupted workers; never leave a forever-PENDING request."""
    maximum = getattr(settings, "SUBMISSION_PENDING_TIMEOUT", 180)
    if submission.status == "PENDING" and (timezone.now() - submission.created_at).total_seconds() > maximum:
        Submission.objects.filter(pk=submission.pk, status="PENDING").update(status="JUDGE_ERROR", finished_at=timezone.now(), error_message="评测任务中断或超时；本次不计入成绩，请重新提交。")
        submission.refresh_from_db()
