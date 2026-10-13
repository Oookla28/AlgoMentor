from apps.accounts.models import UserProfile
from core.security.permissions import require_user


def profile_for(user):
    return UserProfile.objects.get_or_create(user=require_user(user))[0]


def update_profile(user,learning_goal: str):
    from core.exceptions import ValidationError
    if not isinstance(learning_goal,str) or len(learning_goal)>200:
        raise ValidationError('学习目标不能超过 200 字。')
    profile=profile_for(user)
    profile.learning_goal=learning_goal.strip()
    profile.save(update_fields=['learning_goal'])
    return profile
