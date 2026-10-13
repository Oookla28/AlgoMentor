"""Persistent per-provider circuit state, updated by actual business calls.

Reading a status never makes an HTTP request. A cooldown only suppresses repeated
failures; the next real request can claim a bounded half-open attempt. DeepSeek
credential errors live in a separate user scope, never in the shared scope.
"""
import hashlib
import json
import logging
import math
import re
from datetime import timedelta
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from apps.agents.models import ServiceAvailability

logger = logging.getLogger('algomentor')
SERVICES = ('deepseek', 'wikipedia', 'code_execution')
PERSONAL_DEEPSEEK_ERRORS = frozenset({
    'INVALID_API_KEY', 'INSUFFICIENT_BALANCE', 'PROVIDER_RATE_LIMITED',
    'MODEL_UNAVAILABLE', 'MODEL_MISMATCH',
})
MODEL_DEEPSEEK_ERRORS = frozenset({'MODEL_UNAVAILABLE', 'MODEL_MISMATCH'})
_REASONS = {
    'INVALID_API_KEY': '个人 DeepSeek 密钥无效，请在设置中更换。',
    'INSUFFICIENT_BALANCE': '个人 DeepSeek 账户余额不足。',
    'PROVIDER_RATE_LIMITED': '当前账户请求受到限流，请稍后重试。',
    'MODEL_UNAVAILABLE': '当前选择的 DeepSeek 模型暂不可用。',
    'MODEL_MISMATCH': '接口返回的模型与当前选择不一致。',
    'EXECUTION_AUTH_REQUIRED': '执行服务需要管理员配置授权。',
    'EXECUTION_RATE_LIMITED': '执行服务暂时限流。',
}


def _fingerprint(service):
    # Never hash or persist credentials. A changed provider address starts UNKNOWN.
    values = {
        'deepseek': [getattr(settings, 'DEEPSEEK_BASE_URL', '')],
        'wikipedia': [getattr(settings, 'WIKIPEDIA_ENABLED', True),
                      getattr(settings, 'WIKIPEDIA_DEFAULT_LANGUAGE', 'zh'),
                      getattr(settings, 'WIKIPEDIA_FALLBACK_LANGUAGE', 'en')],
        'code_execution': [getattr(settings, 'EXECUTION_PROVIDER', 'piston'),
                           getattr(settings, 'PISTON_BASE_URL', ''),
                           getattr(settings, 'JUDGE0_BASE_URL', ''),
                           getattr(settings, 'PISTON_PYTHON_VERSION', '3.x')],
    }
    return hashlib.sha256(json.dumps(values[service], sort_keys=True).encode()).hexdigest()


def _safe_code(code):
    return code if isinstance(code, str) and re.fullmatch(r'[A-Z][A-Z0-9_]{0,79}', code) else 'SERVICE_ERROR'


class ServiceAvailabilityManager:
    def __init__(self, service, user=None, model=None):
        if service not in SERVICES:
            raise ValueError('Unknown external service')
        if user is not None and (service != 'deepseek' or not getattr(user, 'is_authenticated', False)):
            raise ValueError('Only authenticated DeepSeek users have personal service state')
        if model is not None and (user is None or model not in ('deepseek-flash', 'deepseek-v4-pro')):
            raise ValueError('Only configured DeepSeek models have personal model state')
        self.service = service
        self.user = user
        self.model = model
        self.scope = f'user:{user.pk}' + (f':model:{model}' if model else '') if user is not None else 'global'
        self.fingerprint = _fingerprint(service)

    @property
    def interval(self):
        return max(5, min(3600, int(getattr(settings, 'EXTERNAL_SERVICE_CHECK_INTERVAL', 60))))

    def _row(self):
        return ServiceAvailability.objects.filter(service=self.service, scope=self.scope,
                                                  configuration_fingerprint=self.fingerprint).first()

    def _own_snapshot(self):
        row = self._row()
        now = timezone.now()
        retry = max(0, math.ceil((row.next_retry_at - now).total_seconds())) if row and row.next_retry_at else 0
        result = {
            'service': self.service,
            'status': row.status if row else 'UNKNOWN',
            'updated_at': row.updated_at.isoformat() if row else None,
            'last_success_at': row.last_success_at.isoformat() if row and row.last_success_at else None,
            'last_failure_at': row.last_failure_at.isoformat() if row and row.last_failure_at else None,
            'consecutive_failures': row.consecutive_failures if row else 0,
            'error_code': row.error_code if row else '',
            'reason': _REASONS.get(row.error_code, '上次真实调用失败，稍后可重新尝试。') if row and row.error_code else '',
            'retry_after_seconds': retry,
            'can_attempt': retry == 0,
        }
        if self.service == 'wikipedia' and not getattr(settings, 'WIKIPEDIA_ENABLED', True):
            result.update(status='UNAVAILABLE', error_code='WIKIPEDIA_DISABLED',
                          reason='管理员已关闭 Wikipedia 实时检索，可查询已保存的本地缓存。',
                          retry_after_seconds=0, can_attempt=False, status_source='configuration')
        return result

    def snapshot(self):
        own = self._own_snapshot()
        if self.user is None:
            return own
        shared = (ServiceAvailabilityManager(self.service, user=self.user).snapshot() if self.model
                  else ServiceAvailabilityManager(self.service)._own_snapshot())
        # User authentication/model failures must never be visible to another user.
        rank = {'UNKNOWN': 0, 'AVAILABLE': 1, 'DEGRADED': 2, 'UNAVAILABLE': 3}
        chosen = own if rank[own['status']] >= rank[shared['status']] else shared
        result = {**chosen, 'can_attempt': own['can_attempt'] and shared['can_attempt'],
                  'retry_after_seconds': max(own['retry_after_seconds'], shared['retry_after_seconds'])}
        if self.model:
            result['selected_model'] = self.model
        return result

    def can_attempt(self):
        return self.snapshot()['can_attempt']

    def _locked_row(self):
        row, _ = ServiceAvailability.objects.get_or_create(
            service=self.service, scope=self.scope,
            defaults={'user': self.user, 'configuration_fingerprint': self.fingerprint,
                      'updated_at': timezone.now()},
        )
        if row.configuration_fingerprint != self.fingerprint:
            row.configuration_fingerprint = self.fingerprint
            row.status = 'UNKNOWN'
            row.consecutive_failures = 0
            row.error_code = ''
            row.next_retry_at = None
            row.last_success_at = row.last_failure_at = None
        return row

    def begin_attempt(self):
        """Claim a retry after cooldown; AVAILABLE/UNKNOWN regular traffic is allowed."""
        if self.service == 'wikipedia' and not getattr(settings, 'WIKIPEDIA_ENABLED', True):
            return False
        with transaction.atomic():
            row = self._locked_row()
            now = timezone.now()
            if row.next_retry_at and row.next_retry_at > now:
                return False
            if row.status in ('DEGRADED', 'UNAVAILABLE'):
                row.next_retry_at = now + timedelta(seconds=self.interval)
            row.save()
            return True

    def record_success(self):
        with transaction.atomic():
            row = self._locked_row()
            previous = row.status
            row.status = 'AVAILABLE'
            row.updated_at = row.last_success_at = timezone.now()
            row.consecutive_failures = 0
            row.error_code = ''
            row.next_retry_at = None
            row.save()
        if previous != 'AVAILABLE':
            logger.info('external_service service=%s status=AVAILABLE scope=%s', self.service,
                        'personal' if self.user else 'shared')

    def record_failure(self, code, reason=''):
        # Only codes and fixed messages are exposed; raw provider errors can contain keys.
        code = _safe_code(code)
        if self.service == 'deepseek' and self.user is None and code in PERSONAL_DEEPSEEK_ERRORS:
            return  # Defensive boundary: never poison a shared service with a user's key error.
        if self.service == 'deepseek' and self.user is not None and code in MODEL_DEEPSEEK_ERRORS and not self.model:
            return  # A model error cannot disable all the student's other models.
        with transaction.atomic():
            row = self._locked_row()
            previous = row.status
            row.consecutive_failures += 1
            row.status = 'DEGRADED' if row.consecutive_failures == 1 else 'UNAVAILABLE'
            row.updated_at = row.last_failure_at = timezone.now()
            row.error_code = code
            row.next_retry_at = row.updated_at + timedelta(seconds=self.interval)
            row.save()
        if previous != row.status:
            logger.info('external_service service=%s status=%s code=%s scope=%s', self.service,
                        row.status, code, 'personal' if self.user else 'shared')

    def reset(self):
        """A replaced personal key removes its old failure, without claiming readiness."""
        query = ServiceAvailability.objects.filter(service=self.service)
        if self.user is not None and self.model is None:
            query.filter(user=self.user).delete()
        else:
            query.filter(scope=self.scope).delete()


def get_service_statuses(user=None, model=None):
    if user is not None and model is None:
        from apps.accounts.models import UserAPIConfig
        from core.llm.model_registry import get_tier
        tier = UserAPIConfig.objects.filter(user=user).values_list('default_tier', flat=True).first()
        if tier:
            model = get_tier(tier).model
    return [ServiceAvailabilityManager(name, user=user if name == 'deepseek' else None,
                                       model=model if name == 'deepseek' else None).snapshot()
            for name in SERVICES]


def ensure_deepseek_attempt(user, model=None):
    """No probe: authorize a real chat/report call after independent cooldowns."""
    from core.exceptions import LLMProviderError
    shared = ServiceAvailabilityManager('deepseek')
    personal = ServiceAvailabilityManager('deepseek', user=user)
    selected = ServiceAvailabilityManager('deepseek', user=user, model=model) if model else None
    if not shared.can_attempt() or not personal.can_attempt() or (selected and not selected.can_attempt()):
        raise LLMProviderError('DeepSeek 暂不可用，可继续使用本地知识、学习记录和算法演示；稍后重试。',
                               code='DEEPSEEK_TEMPORARILY_UNAVAILABLE', status_code=503)
    if not shared.begin_attempt() or not personal.begin_attempt() or (selected and not selected.begin_attempt()):
        raise LLMProviderError('DeepSeek 正在等待恢复，请稍后重试。',
                               code='DEEPSEEK_TEMPORARILY_UNAVAILABLE', status_code=503)
