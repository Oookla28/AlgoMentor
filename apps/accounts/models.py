from django.conf import settings
from django.db import models


class UserProfile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='profile')
    learning_goal = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class UserAPIConfig(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='api_config')
    encrypted_api_key = models.TextField(blank=True)
    key_hint = models.CharField(max_length=20, blank=True)
    default_tier = models.CharField(max_length=12, default='fast', choices=[('fast','DeepSeek 极速'),('deep','DeepSeek 深度'),('expert','DeepSeek 专家')])
    reasoning_effort = models.CharField(max_length=8, default='high', choices=[('low','low'),('high','high'),('max','max')])
    last_status = models.CharField(max_length=40, default='NOT_CONFIGURED')
    last_checked_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def configured(self):
        return bool(self.encrypted_api_key)


class APIUsageRecord(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='api_usage')
    model = models.CharField(max_length=60)
    tier = models.CharField(max_length=12)
    created_at = models.DateTimeField(auto_now_add=True)
    duration_ms = models.PositiveIntegerField(default=0)
    input_tokens = models.PositiveIntegerField(null=True, blank=True)
    output_tokens = models.PositiveIntegerField(null=True, blank=True)
    status = models.CharField(max_length=30, default='PENDING')
    error_code = models.CharField(max_length=60, blank=True)
    purpose = models.CharField(max_length=30, default='chat')

    class Meta:
        indexes = [models.Index(fields=['user', 'created_at'])]
        ordering = ['-created_at']


class DailyAPIBudget(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    day = models.DateField()
    requests = models.PositiveIntegerField(default=0)
    charged_tokens = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['user','day'], name='unique_user_daily_budget')]


class MinuteAPIBudget(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.CASCADE)
    minute = models.DateTimeField()
    requests = models.PositiveIntegerField(default=0)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['user','minute'],name='unique_user_minute_budget')]
