"""Fernet envelope encryption; first key encrypts, following keys decrypt during rotation."""
from cryptography.fernet import Fernet, MultiFernet, InvalidToken
from django.conf import settings
from core.exceptions import BusinessError


def cipher() -> MultiFernet:
    keys = getattr(settings, 'APP_ENCRYPTION_KEYS', None)
    if not keys:
        keys = [getattr(settings, 'APP_ENCRYPTION_KEY', '')] + [k.strip() for k in getattr(settings, 'APP_ENCRYPTION_PREVIOUS_KEYS', '').split(',') if k.strip()]
    if isinstance(keys, str):
        keys = [k.strip() for k in keys.split(',') if k.strip()]
    try:
        return MultiFernet([Fernet(k.encode() if isinstance(k, str) else k) for k in keys])
    except (ValueError, TypeError):
        raise BusinessError('服务器尚未配置有效的密钥加密主密钥，请联系管理员。', code='ENCRYPTION_NOT_CONFIGURED', status_code=503) from None


def encrypt_secret(secret: str) -> str:
    return cipher().encrypt(secret.encode()).decode()


def decrypt_secret(token: str) -> str:
    try:
        return cipher().decrypt(token.encode()).decode()
    except (InvalidToken, UnicodeDecodeError):
        raise BusinessError('密钥无法解密，请重新配置或联系管理员恢复加密主密钥。', code='CREDENTIAL_DECRYPTION_FAILED', status_code=503) from None


def rotate_secret(token: str) -> str:
    try:
        return cipher().rotate(token.encode()).decode()
    except InvalidToken:
        raise BusinessError('密钥轮换失败，请检查旧加密主密钥。', code='KEY_ROTATION_FAILED', status_code=503) from None
