from django.conf import settings
from django.db import models


class DomainPack(models.Model):
    pack_id = models.CharField(max_length=100)
    version = models.CharField(max_length=32)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, default='')
    manifest = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [('pack_id', 'version')]
        ordering = ['pack_id', '-created_at']


class TaskPack(models.Model):
    task_id = models.CharField(max_length=100)
    domain_pack_id = models.CharField(max_length=100)
    version = models.CharField(max_length=32)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, default='')
    manifest = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [('task_id', 'version')]
        ordering = ['task_id']


class ToolSpecRecord(models.Model):
    tool_id = models.CharField(max_length=100)
    version = models.CharField(max_length=32)
    name = models.CharField(max_length=200)
    spec = models.JSONField(default=dict, blank=True)
    enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [('tool_id', 'version')]
        ordering = ['tool_id']


class AgentRun(models.Model):
    STATUS = [('RUNNING', '运行中'), ('COMPLETED', '已完成'), ('ABSTAINED', '拒答'), ('FAILED', '失败')]
    run_id = models.CharField(max_length=64, unique=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='platform_agent_runs')
    domain = models.CharField(max_length=100, default='data_structures')
    query = models.TextField()
    mode = models.CharField(max_length=30, default='adaptive')
    status = models.CharField(max_length=20, default='RUNNING', choices=STATUS)
    answer_text = models.TextField(blank=True, default='')
    citations = models.JSONField(default=list, blank=True)
    evidence_count = models.PositiveIntegerField(default=0)
    step_count = models.PositiveIntegerField(default=0)
    budget = models.JSONField(default=dict, blank=True)
    metrics = models.JSONField(default=dict, blank=True)
    error_code = models.CharField(max_length=100, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']


class AgentStep(models.Model):
    run = models.ForeignKey(AgentRun, on_delete=models.CASCADE, related_name='steps')
    step_id = models.CharField(max_length=64)
    parent_step_id = models.CharField(max_length=64, blank=True, default='')
    hop_id = models.PositiveSmallIntegerField(default=0)
    step_type = models.CharField(max_length=30)
    input_summary = models.TextField(blank=True, default='')
    output_summary = models.TextField(blank=True, default='')
    evidence_ids = models.JSONField(default=list, blank=True)
    decision = models.CharField(max_length=50, blank=True, default='')
    reason_code = models.CharField(max_length=100, blank=True, default='')
    latency_ms = models.PositiveIntegerField(default=0)
    tokens = models.PositiveIntegerField(default=0)
    tool_calls = models.PositiveSmallIntegerField(default=0)
    provider = models.CharField(max_length=100, blank=True, default='')
    index_version = models.CharField(max_length=100, blank=True, default='')
    model = models.CharField(max_length=100, blank=True, default='')
    failure_code = models.CharField(max_length=100, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [('run', 'step_id')]
        ordering = ['run', 'created_at', 'id']


class Evidence(models.Model):
    evidence_id = models.CharField(max_length=150)
    run = models.ForeignKey(AgentRun, on_delete=models.CASCADE, related_name='evidence')
    parent_id = models.CharField(max_length=150, blank=True, default='')
    document_id = models.IntegerField(null=True, blank=True)
    chunk_id = models.CharField(max_length=100, blank=True, default='')
    source_uri = models.CharField(max_length=500, blank=True, default='')
    modality = models.CharField(max_length=30, default='text')
    page = models.PositiveIntegerField(null=True, blank=True)
    char_start = models.PositiveIntegerField(null=True, blank=True)
    char_end = models.PositiveIntegerField(null=True, blank=True)
    content_hash = models.CharField(max_length=64, blank=True, default='')
    source_version = models.CharField(max_length=32, blank=True, default='1')
    valid_from = models.DateTimeField(null=True, blank=True)
    valid_to = models.DateTimeField(null=True, blank=True)
    authority_score = models.FloatField(default=0.0)
    retrieval_score = models.FloatField(default=0.0)
    verifier_score = models.FloatField(default=0.0)
    content = models.TextField(blank=True, default='')
    heading_path = models.CharField(max_length=500, blank=True, default='')
    provider = models.CharField(max_length=100, blank=True, default='')
    index_version = models.CharField(max_length=100, blank=True, default='')

    class Meta:
        unique_together = [('run', 'evidence_id')]
        ordering = ['run', '-retrieval_score']


class Claim(models.Model):
    claim_id = models.CharField(max_length=100)
    run = models.ForeignKey(AgentRun, on_delete=models.CASCADE, related_name='claims')
    text = models.TextField()
    polarity = models.CharField(max_length=20, default='positive')
    numbers = models.JSONField(default=list, blank=True)
    units = models.JSONField(default=list, blank=True)
    versions = models.JSONField(default=list, blank=True)
    years = models.JSONField(default=list, blank=True)
    evidence_ids = models.JSONField(default=list, blank=True)
    status = models.CharField(max_length=30, default='supported')

    class Meta:
        unique_together = [('run', 'claim_id')]
        ordering = ['run', 'claim_id']


class ConflictSet(models.Model):
    conflict_id = models.CharField(max_length=100)
    run = models.ForeignKey(AgentRun, on_delete=models.CASCADE, related_name='conflict_sets')
    conflict_type = models.CharField(max_length=30)
    confidence = models.FloatField(default=0.0)
    verdict = models.CharField(max_length=20, default='UNRESOLVED')
    claims = models.JSONField(default=list, blank=True)
    explanation = models.TextField(blank=True, default='')

    class Meta:
        unique_together = [('run', 'conflict_id')]
        ordering = ['run', 'conflict_id']


class EvaluationCase(models.Model):
    case_id = models.CharField(max_length=100)
    dataset = models.CharField(max_length=100, default='platform')
    question = models.TextField()
    domain = models.CharField(max_length=100, default='data_structures')
    difficulty = models.CharField(max_length=30, blank=True, default='')
    answerable = models.BooleanField(default=True)
    payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [('case_id', 'dataset')]
        ordering = ['dataset', 'case_id']


class EvaluationRun(models.Model):
    run_id = models.CharField(max_length=64, unique=True)
    dataset = models.CharField(max_length=100, default='platform')
    config_hash = models.CharField(max_length=64, blank=True, default='')
    dataset_hash = models.CharField(max_length=64, blank=True, default='')
    git_sha = models.CharField(max_length=64, blank=True, default='')
    status = models.CharField(max_length=20, default='RUNNING')
    metrics = models.JSONField(default=dict, blank=True)
    failures = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
