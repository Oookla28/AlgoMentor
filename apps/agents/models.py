import uuid
from django.conf import settings
from django.db import models


class AgentTrace(models.Model):
    id = models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.CASCADE,related_name='agent_traces')
    session_id = models.CharField(max_length=80,blank=True)
    selected_model = models.CharField(max_length=60)
    tier = models.CharField(max_length=12)
    status = models.CharField(max_length=16,default='RUNNING')
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True,blank=True)
    duration_ms = models.PositiveIntegerField(default=0)
    error_type = models.CharField(max_length=80,blank=True)
    class Meta:
        ordering = ['-started_at']
        indexes = [models.Index(fields=['user','started_at'])]


class ToolInvocation(models.Model):
    trace = models.ForeignKey(AgentTrace,on_delete=models.CASCADE,related_name='invocations')
    tool_name = models.CharField(max_length=80)
    input_summary = models.CharField(max_length=500)
    output_summary = models.CharField(max_length=500,blank=True)
    started_at = models.DateTimeField(auto_now_add=True)
    duration_ms = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=20,default='RUNNING')
    error_type = models.CharField(max_length=80,blank=True)
    class Meta:
        ordering = ['started_at','id']
