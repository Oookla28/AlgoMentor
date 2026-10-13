from apps.learning.services.progress_service import get_learning_summary
from core.security.permissions import require_user
from django.utils import timezone


def weekly_statistics(user) -> dict:
    require_user(user)
    # Calendar week in the application's Asia/Shanghai timezone, from Monday midnight.
    return get_learning_summary(user,days=timezone.localdate().weekday()+1)


def validated_metrics(statistics: dict) -> dict:
    fields=('total_submissions','accepted_submissions','attempted_problems','solved_problems','accuracy','excluded_infrastructure_submissions')
    return {field:statistics[field] for field in fields}
