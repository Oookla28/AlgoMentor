from django.db import transaction
from django.utils import timezone
from core.exceptions import AuthenticationError, ValidationError
from core.security.encryption import encrypt_secret, decrypt_secret, rotate_secret
from core.security.permissions import require_user
from core.llm.model_registry import get_tier
from apps.accounts.models import UserAPIConfig


def get_config(user) -> UserAPIConfig:
    require_user(user)
    return UserAPIConfig.objects.get_or_create(user=user)[0]


def get_api_key(user) -> str:
    config = get_config(user)
    if not config.configured:
        raise AuthenticationError('请先在个人设置中配置自己的 DeepSeek API Key。', code='API_KEY_REQUIRED', status_code=428)
    return decrypt_secret(config.encrypted_api_key)


@transaction.atomic
def save_config(user, api_key: str = '', default_tier: str = 'fast', reasoning_effort: str = 'high', learning_goal: str | None = None) -> UserAPIConfig:
    require_user(user)
    get_tier(default_tier)
    if reasoning_effort not in ('low','high','max'):
        raise ValidationError('请选择有效的推理强度。')
    config = get_config(user)
    key = api_key.strip()
    if key:
        if len(key) < 12 or len(key) > 256 or any(ch.isspace() for ch in key):
            raise ValidationError('API Key 格式无效，请检查复制内容。')
        config.encrypted_api_key = encrypt_secret(key)
        config.key_hint = '••••' + key[-4:]
        config.last_status = 'UNTESTED'
        config.last_checked_at = None
    config.default_tier = default_tier
    config.reasoning_effort = reasoning_effort
    config.save()
    if key:
        from core.services.availability import ServiceAvailabilityManager
        ServiceAvailabilityManager('deepseek', user=user).reset()
    if learning_goal is not None:
        from apps.accounts.services.profile_service import update_profile
        update_profile(user,learning_goal)
    return config


def delete_key(user) -> None:
    config = get_config(user)
    config.encrypted_api_key = ''
    config.key_hint = ''
    config.last_status = 'NOT_CONFIGURED'
    config.last_checked_at = None
    config.save()
    from core.services.availability import ServiceAvailabilityManager
    ServiceAvailabilityManager('deepseek', user=user).reset()


def rotate_key(user) -> None:
    config = get_config(user)
    if config.configured:
        config.encrypted_api_key = rotate_secret(config.encrypted_api_key)
        config.save(update_fields=['encrypted_api_key','updated_at'])


def public_config(user) -> dict:
    config = get_config(user)
    return {'configured': config.configured, 'key_hint': config.key_hint, 'default_tier': config.default_tier, 'reasoning_effort': config.reasoning_effort, 'last_status': config.last_status, 'last_checked_at': config.last_checked_at.isoformat() if config.last_checked_at else None}


def record_connection_status(user, status: str):
    UserAPIConfig.objects.filter(user=require_user(user)).update(last_status=status[:40], last_checked_at=timezone.now())
