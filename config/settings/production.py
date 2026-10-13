from .base import *
from django.core.exceptions import ImproperlyConfigured
MIDDLEWARE.insert(1, 'whitenoise.middleware.WhiteNoiseMiddleware')
STORAGES = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage'},
}
if not SECRET_KEY or SECRET_KEY == 'development-only-change-before-production' or not APP_ENCRYPTION_KEY:
    raise ImproperlyConfigured('生产环境必须配置 DJANGO_SECRET_KEY 与 APP_ENCRYPTION_KEY。')
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_SSL_REDIRECT = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
