import uuid
from django.conf import settings
from django.db import models


class LearningReport(models.Model):
    id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False)
    user=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.CASCADE,related_name='learning_reports')
    created_at=models.DateTimeField(auto_now_add=True)
    period_start=models.DateTimeField()
    period_end=models.DateTimeField()
    statistics=models.JSONField(default=dict)
    markdown=models.TextField()
    selected_model=models.CharField(max_length=60)
    validated=models.BooleanField(default=False)
    class Meta:
        ordering=['-created_at']
        indexes=[models.Index(fields=['user','created_at'])]


class ReportTask(models.Model):
    class Status(models.TextChoices):
        PENDING='PENDING','等待 Worker'
        RUNNING='RUNNING','生成中'
        SUCCESS='SUCCESS','已完成'
        FAILED='FAILED','失败'
        TIMEOUT='TIMEOUT','超时'
    id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False)
    user=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.CASCADE,related_name='report_tasks')
    report=models.OneToOneField(LearningReport,on_delete=models.SET_NULL,null=True,blank=True,related_name='task')
    status=models.CharField(max_length=16,choices=Status.choices,default=Status.PENDING)
    tier=models.CharField(max_length=12,default='deep')
    created_at=models.DateTimeField(auto_now_add=True)
    started_at=models.DateTimeField(null=True,blank=True)
    finished_at=models.DateTimeField(null=True,blank=True)
    deadline_at=models.DateTimeField(null=True,blank=True)
    error_code=models.CharField(max_length=80,blank=True)
    error_message=models.CharField(max_length=500,blank=True)
    statistics=models.JSONField(default=dict)
    class Meta:
        ordering=['-created_at']
        indexes=[models.Index(fields=['status','created_at']),models.Index(fields=['user','created_at'])]
