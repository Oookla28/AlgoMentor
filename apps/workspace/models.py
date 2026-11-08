"""Private workspaces, document membership, task artifacts and skill activations.

A workspace is the authorization boundary for user-uploaded material. Shared
course spaces stay readable to every signed-in learner but are only writable by
staff/editors; personal spaces are never visible through the compatibility APIs.
"""

import uuid

from django.conf import settings
from django.db import models


def _uuid_hex():
    return uuid.uuid4().hex


class Workspace(models.Model):
    VISIBILITIES = [('private', '私有'), ('shared', '共享')]
    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=64, unique=True, default=_uuid_hex)
    description = models.TextField(blank=True, default='')
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='owned_workspaces',
    )
    visibility = models.CharField(max_length=20, choices=VISIBILITIES, default='private', db_index=True)
    domain_pack_id = models.CharField(max_length=100, default='generic')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_archived = models.BooleanField(default=False, db_index=True)

    class Meta:
        ordering = ['-updated_at', 'id']

    def __str__(self):
        return self.name


class WorkspaceMember(models.Model):
    ROLES = [('editor', '可编辑'), ('viewer', '只读')]
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name='members')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='workspace_memberships')
    role = models.CharField(max_length=20, choices=ROLES, default='viewer')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [('workspace', 'user')]
        ordering = ['workspace', 'created_at']

    def __str__(self):
        return f'{self.workspace_id}:{self.user_id}:{self.role}'


class WorkspaceDocument(models.Model):
    STATUS = [
        ('processing', '解析中'),
        ('ready', '可检索'),
        ('partial', '部分可用'),
        ('failed', '解析失败'),
        ('removed', '已移除'),
    ]
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name='documents')
    document = models.ForeignKey(
        'knowledge.KnowledgeDocument', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='workspace_links',
    )
    added_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    original_name = models.CharField(max_length=255, blank=True, default='')
    status = models.CharField(max_length=20, choices=STATUS, default='processing', db_index=True)
    error_message = models.TextField(blank=True, default='')
    file_path = models.CharField(max_length=500, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    removed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = [('workspace', 'document')]
        ordering = ['workspace', '-created_at', 'id']

    def __str__(self):
        return f'{self.workspace_id}:{self.original_name}'


class TaskArtifact(models.Model):
    FORMATS = [('markdown', 'Markdown'), ('html', 'HTML'), ('diff', 'Unified diff')]
    artifact_id = models.CharField(max_length=64, unique=True, default=_uuid_hex)
    run = models.ForeignKey('platform.AgentRun', on_delete=models.CASCADE, related_name='artifacts')
    kind = models.CharField(max_length=50, default='answer')
    format = models.CharField(max_length=20, choices=FORMATS, default='markdown')
    filename = models.CharField(max_length=200, default='answer.md')
    content = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['run', 'created_at', 'id']

    def __str__(self):
        return f'{self.kind}:{self.filename}'


class SkillActivation(models.Model):
    STATUS = [
        ('activated', '已激活'),
        ('skipped', '已跳过'),
        ('failed', '失败'),
        ('revoked', '已撤销'),
    ]
    run = models.ForeignKey('platform.AgentRun', on_delete=models.CASCADE, related_name='skill_activations')
    skill_id = models.CharField(max_length=100)
    version = models.CharField(max_length=32, default='1.0.0')
    content_hash = models.CharField(max_length=64, blank=True, default='')
    trigger = models.CharField(max_length=200, blank=True, default='')
    tool_scope = models.JSONField(default=list, blank=True)
    status = models.CharField(max_length=20, choices=STATUS, default='activated')
    result_summary = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['run', 'created_at', 'id']
        unique_together = [('run', 'skill_id', 'version')]

    def __str__(self):
        return f'{self.skill_id}@{self.version}'


class TaskFeedback(models.Model):
    run = models.ForeignKey('platform.AgentRun', on_delete=models.CASCADE, related_name='feedback')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='task_feedback')
    rating = models.SmallIntegerField(default=0, choices=[(-1, '未解决'), (0, '中立'), (1, '有帮助')])
    comment = models.CharField(max_length=500, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [('run', 'user')]
        ordering = ['-created_at']


class WorkerHeartbeat(models.Model):
    worker_id = models.CharField(max_length=64, unique=True)
    host = models.CharField(max_length=100, blank=True, default='')
    current_run_id = models.CharField(max_length=64, blank=True, default='')
    started_at = models.DateTimeField(auto_now_add=True)
    last_seen = models.DateTimeField(db_index=True)

    class Meta:
        ordering = ['-last_seen']

    def __str__(self):
        return self.worker_id
