from django.utils import timezone
from django.db import transaction
from apps.learning.models import MistakeRecord


def update_mistakes(submission):
    if not submission.is_valid:
        return
    if submission.status == "ACCEPTED":
        MistakeRecord.objects.filter(user=submission.user, problem=submission.problem, resolved=False).update(resolved=True, resolved_at=timezone.now())
    else:
        from apps.problems.services.diagnosis_service import diagnose_submission
        diagnosis = diagnose_submission(submission)
        MistakeRecord.objects.get_or_create(submission=submission, defaults={"user": submission.user, "problem": submission.problem,
            "error_type": submission.status, "failure_reason": diagnosis["summary"]})


def review_mistake(user, mistake_id):
    mistake = MistakeRecord.objects.get(pk=mistake_id, user=user)
    mistake.last_reviewed_at = timezone.now()
    mistake.save(update_fields=["last_reviewed_at"])
    # Review contacts are recorded, but never treated as correct responses.
    from apps.learning.models import LearningActivity
    for point in mistake.problem.knowledge_points.all():
        LearningActivity.objects.create(user=user, knowledge_point=point, event_type="review", correct=None,
                                       event_key=f"review:{mistake.pk}:{timezone.now().timestamp()}")
    return mistake


@transaction.atomic
def store_ai_diagnosis(user, submission, text, level, model):
    """Own the mistake update and record real delivered hint evidence."""
    import uuid
    from apps.learning.models import LearningActivity
    if submission.user_id != user.pk:
        from core.exceptions import AuthenticationError
        raise AuthenticationError("不能更新其他学生的诊断。", status_code=403)
    mistake = MistakeRecord.objects.get(user=user, submission=submission)
    mistake.ai_diagnosis = f"[层级 {level} · {model}]\n{text[:12000]}"
    mistake.save(update_fields=["ai_diagnosis"])
    event_key = f"ai_diagnosis:{submission.pk}:{level}:{uuid.uuid4().hex}"
    for point in submission.problem.knowledge_points.all():
        LearningActivity.objects.create(user=user, submission=submission, knowledge_point=point, event_type="hint",
            correct=None, hints_used=1, event_key=event_key)
    return mistake
