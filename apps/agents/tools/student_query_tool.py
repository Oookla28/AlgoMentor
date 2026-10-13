from apps.learning.services.progress_service import get_learning_summary
from core.security.permissions import require_user


def query_student_learning(user,days: int = 7) -> dict:
    require_user(user)
    return get_learning_summary(user,days=max(1,min(int(days),90)))
