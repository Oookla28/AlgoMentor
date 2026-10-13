from datetime import timedelta
from django.conf import settings
from django.db import transaction
from django.db.models import F, Sum
from django.utils import timezone
from apps.accounts.models import APIUsageRecord, DailyAPIBudget, MinuteAPIBudget
from core.exceptions import BusinessError
from core.security.permissions import require_user


def reserve_request(user, reservation: int) -> tuple[int, int]:
    require_user(user)
    request_limit = getattr(settings, 'LLM_DAILY_REQUEST_LIMIT', 100)
    token_limit = getattr(settings, 'LLM_DAILY_TOKEN_LIMIT', 200000)
    with transaction.atomic():
        budget, _ = DailyAPIBudget.objects.get_or_create(user=user, day=timezone.localdate())
        changed = DailyAPIBudget.objects.filter(pk=budget.pk, requests__lt=request_limit, charged_tokens__lte=max(0, token_limit-reservation)).update(requests=F('requests')+1, charged_tokens=F('charged_tokens')+reservation)
        if not changed or reservation > token_limit:
            if changed:
                DailyAPIBudget.objects.filter(pk=budget.pk).update(charged_tokens=F('charged_tokens')-reservation, requests=F('requests')-1)
            raise BusinessError('今日 AI 请求次数或 Token 预算已达到上限，请明日再试。', code='DAILY_BUDGET_EXCEEDED', status_code=429)
        minute=timezone.now().replace(second=0,microsecond=0)
        rate,_=MinuteAPIBudget.objects.get_or_create(user=user,minute=minute)
        changed=MinuteAPIBudget.objects.filter(pk=rate.pk,requests__lt=getattr(settings,'LLM_REQUESTS_PER_MINUTE',10)).update(requests=F('requests')+1)
        if not changed:
            # The enclosing atomic block rolls back the daily reservation too.
            raise BusinessError('请求过于频繁，请稍后再试。',code='RATE_LIMITED',status_code=429)
    return budget.pk, reservation


def settle_request(budget_id: int, reserved: int, actual: int | None):
    if actual is not None and actual < reserved:
        DailyAPIBudget.objects.filter(pk=budget_id).update(charged_tokens=F('charged_tokens')-(reserved-actual))
    elif actual is not None and actual > reserved:
        DailyAPIBudget.objects.filter(pk=budget_id).update(charged_tokens=F('charged_tokens')+(actual-reserved))


def monthly_usage(user) -> dict:
    require_user(user)
    month = timezone.localdate().replace(day=1)
    records = APIUsageRecord.objects.filter(user=user,created_at__date__gte=month)
    sums = records.aggregate(input_tokens=Sum('input_tokens'),output_tokens=Sum('output_tokens'))
    return {'requests':records.count(),'input_tokens':sums['input_tokens'] or 0,'output_tokens':sums['output_tokens'] or 0,'usage_missing_requests':records.filter(status='SUCCESS',input_tokens__isnull=True).count()}
