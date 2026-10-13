from core.exceptions import AuthenticationError


def require_user(user):
    if not user or not user.is_authenticated or not user.is_active or not user.pk:
        raise AuthenticationError('请先登录有效账户。')
    return user
