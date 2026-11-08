"""Task acceptance, cancellation, retry, queue claiming and recovery."""

from datetime import timedelta
import socket
import time
import uuid

from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone

from core.exceptions import BusinessError, ValidationError
from core.security.permissions import require_user

from apps.platform.domains import get_domain_pack, get_task_pack
from apps.platform.models import AgentRun

from ..models import TaskArtifact, TaskFeedback, WorkerHeartbeat, Workspace
from ..permissions import can_manage, ensure_readable
from .documents import active_document_ids
from .executor import TASK_TYPES, budget_for, task_budget_dict

ACTIVE_STATUSES = ('QUEUED', 'RUNNING', 'WAITING_USER')
TERMINAL_STATUSES = ('COMPLETED', 'SUCCEEDED', 'PARTIAL', 'ABSTAINED', 'FAILED', 'CANCELLED')
WORKER_ONLINE_SECONDS = getattr(settings, 'WORKBENCH_WORKER_ONLINE_SECONDS', 60)


def _rate_limit(user):
    key = f'workbench-task-rate:{user.pk}:{int(time.time() // 60)}'
    count = cache.get(key, 0)
    if count >= 8:
        raise BusinessError('任务提交过于频繁，请稍后再试。', code='RATE_LIMITED', status_code=429)
    cache.set(key, count + 1, 70)


def _validate_task(task_type, workspace):
    if task_type not in TASK_TYPES:
        raise ValidationError('未知任务类型。', code='TASK_TYPE_INVALID')
    task_pack = get_task_pack(task_type, workspace.domain_pack_id)
    if task_pack is None:
        raise ValidationError(
            f'当前空间（{workspace.domain_pack_id}）不支持该任务，请切换到匹配的领域空间。',
            code='TASK_PACK_NOT_AVAILABLE',
        )
    if get_domain_pack(workspace.domain_pack_id) is None:
        raise ValidationError('当前空间的领域包不可用。', code='DOMAIN_PACK_NOT_FOUND')
    active_count = len(active_document_ids(workspace))
    minimum = 2 if task_type == 'paper_comparison' else 1
    if active_count < minimum:
        raise ValidationError(
            f'该任务至少需要 {minimum} 份可检索资料，当前空间只有 {active_count} 份。',
            code='WORKSPACE_INSUFFICIENT_DOCUMENTS',
        )
    return task_pack


def create_task(user, workspace, task_type, query, requested_mode='standard', skip_rate_limit=False):
    require_user(user)
    ensure_readable(user, workspace)
    query = (query or '').strip()
    if not query or len(query) > 2000:
        raise ValidationError('任务目标须为 1 至 2000 字。', code='TASK_QUERY_INVALID')
    requested_mode = str(requested_mode or 'standard')
    if requested_mode not in ('quick', 'standard', 'deep'):
        requested_mode = 'standard'
    task_pack = _validate_task(task_type, workspace)
    active = AgentRun.objects.filter(user=user, status__in=ACTIVE_STATUSES).count()
    if active >= 3:
        raise BusinessError('当前已有 3 个任务在排队或运行，请稍后再提交。', code='TASK_CONCURRENCY_LIMIT', status_code=429)
    if not skip_rate_limit:
        _rate_limit(user)
    run = AgentRun.objects.create(
        run_id=uuid.uuid4().hex,
        user=user,
        workspace=workspace,
        domain=workspace.domain_pack_id,
        task_type=task_type,
        task_pack_id=task_pack.task_id,
        query=query,
        mode='adaptive',
        requested_mode=requested_mode,
        status='QUEUED',
        stage='排队中',
        budget=task_budget_dict(requested_mode),
        input_payload={'workspace_id': workspace.pk, 'task_type': task_type},
        metrics={
            'provider': getattr(settings, 'EMBEDDING_PROVIDER', ''),
            'model': getattr(settings, 'EMBEDDING_MODEL', ''),
            'workspace_id': workspace.pk,
            'requested_mode': requested_mode,
        },
    )
    return run


def cancel_task(user, run):
    require_user(user)
    if run.user_id != user.pk and not (run.workspace_id and can_manage(user, run.workspace)):
        raise BusinessError('无权取消该任务。', code='TASK_PERMISSION_DENIED', status_code=403)
    if run.status in TERMINAL_STATUSES:
        return run
    run.cancel_requested = True
    if run.status == 'QUEUED':
        run.status = 'CANCELLED'
        run.stage = '已取消'
        run.finished_at = timezone.now()
        run.error_code = 'CANCELLED_BY_USER'
        run.save(update_fields=['cancel_requested', 'status', 'stage', 'finished_at', 'error_code'])
    else:
        run.save(update_fields=['cancel_requested'])
    return run


def retry_task(user, run):
    require_user(user)
    if run.user_id != user.pk and not (run.workspace_id and can_manage(user, run.workspace)):
        raise BusinessError('无权重试该任务。', code='TASK_PERMISSION_DENIED', status_code=403)
    if run.status not in ('FAILED', 'PARTIAL', 'CANCELLED', 'ABSTAINED'):
        raise ValidationError('只有失败、部分完成、已取消或拒答的任务可以重试。', code='TASK_NOT_RETRYABLE')
    workspace = run.workspace
    if workspace is None:
        raise ValidationError('原任务没有关联工作空间，不能重试。', code='WORKSPACE_MISSING')
    new_run = create_task(user, workspace, run.task_type, run.query, run.requested_mode)
    new_run.input_payload = {**(new_run.input_payload or {}), 'retry_of': run.run_id}
    new_run.metrics = {**(new_run.metrics or {}), 'retry_of': run.run_id}
    new_run.save(update_fields=['input_payload', 'metrics'])
    return new_run


def submit_feedback(user, run, rating, comment=''):
    require_user(user)
    if run.user_id != user.pk:
        raise BusinessError('只能反馈自己的任务。', code='TASK_PERMISSION_DENIED', status_code=403)
    try:
        rating = int(rating)
    except (TypeError, ValueError):
        raise ValidationError('反馈评分无效。')
    if rating not in (-1, 0, 1):
        raise ValidationError('反馈评分无效。')
    row, _created = TaskFeedback.objects.update_or_create(
        run=run, user=user, defaults={'rating': rating, 'comment': (comment or '').strip()[:500]},
    )
    return row


def claim_next(worker_id, lease_seconds=120):
    now = timezone.now()
    with transaction.atomic():
        run = (
            AgentRun.objects.select_for_update()
            .filter(status='QUEUED', cancel_requested=False)
            .order_by('created_at', 'pk').first()
        )
        if run is None:
            return None
        run.status = 'RUNNING'
        run.stage = '读取资料'
        run.attempts += 1
        run.worker_id = worker_id
        run.heartbeat_at = now
        run.lease_expires_at = now + timedelta(seconds=lease_seconds)
        run.save(update_fields=['status', 'stage', 'attempts', 'worker_id', 'heartbeat_at', 'lease_expires_at'])
        return run


def recover_stale_runs(max_attempts=2):
    now = timezone.now()
    recovered = 0
    failed = 0
    stale = list(AgentRun.objects.filter(status='RUNNING', lease_expires_at__lt=now)[:20])
    for run in stale:
        if run.cancel_requested:
            run.status = 'CANCELLED'
            run.stage = '已取消'
            run.error_code = 'CANCELLED_BY_USER'
            run.finished_at = now
            run.save(update_fields=['status', 'stage', 'error_code', 'finished_at'])
            recovered += 1
        elif run.attempts >= max_attempts:
            run.status = 'FAILED'
            run.stage = '执行失败'
            run.error_code = 'WORKER_LOST'
            run.finished_at = now
            run.save(update_fields=['status', 'stage', 'error_code', 'finished_at'])
            failed += 1
        else:
            run.status = 'QUEUED'
            run.stage = '等待恢复'
            run.error_code = 'WORKER_LEASE_EXPIRED'
            run.worker_id = ''
            run.save(update_fields=['status', 'stage', 'error_code', 'worker_id'])
            recovered += 1
    return {'requeued': recovered, 'failed': failed}


def touch_heartbeat(worker_id, current_run_id=''):
    now = timezone.now()
    row, _created = WorkerHeartbeat.objects.update_or_create(
        worker_id=worker_id,
        defaults={'last_seen': now, 'current_run_id': current_run_id, 'host': socket.gethostname()[:100]},
    )
    return row


def worker_status():
    latest = WorkerHeartbeat.objects.order_by('-last_seen').first()
    if latest is None:
        return {'online': False, 'state': 'not_started', 'worker_id': '', 'last_seen': '', 'current_run_id': ''}
    online = (timezone.now() - latest.last_seen).total_seconds() <= WORKER_ONLINE_SECONDS
    return {
        'online': online,
        'state': 'online' if online else 'offline',
        'worker_id': latest.worker_id,
        'last_seen': latest.last_seen.isoformat(),
        'current_run_id': latest.current_run_id,
        'host': latest.host,
    }


def serialize_task(run, include_steps=False, include_evidence=True, staff=False):
    artifacts = [
        {
            'artifact_id': artifact.artifact_id, 'kind': artifact.kind, 'format': artifact.format,
            'filename': artifact.filename,
            'download_url': f'/workbench/artifacts/{artifact.artifact_id}/download/',
        }
        for artifact in TaskArtifact.objects.filter(run=run).order_by('created_at')
    ]
    activations = []
    for item in run.skill_activations.all():
        activation = {
            'skill_id': item.skill_id, 'version': item.version, 'status': item.status,
            'trigger': item.trigger, 'result_summary': item.result_summary,
        }
        if staff:
            activation['content_hash'] = item.content_hash
            activation['tool_scope'] = item.tool_scope
        activations.append(activation)
    metrics = run.metrics or {}
    if not staff:
        # Learner-facing payload: no provider/model/token/tool internals.
        metrics = {
            'latency_ms': metrics.get('latency_ms', 0),
            'conflicts': metrics.get('conflicts', 0),
            'documents_compared': metrics.get('documents_compared', 0),
            'findings': metrics.get('findings', 0),
            'execution_status': metrics.get('execution_status', ''),
        }
    payload = {
        'run_id': run.run_id,
        'status': run.status,
        'status_label': dict(AgentRun.STATUS).get(run.status, run.status),
        'stage': run.stage,
        'task_type': run.task_type,
        'task_pack_id': run.task_pack_id,
        'domain': run.domain,
        'workspace_id': run.workspace_id,
        'workspace_name': run.workspace.name if run.workspace_id else '',
        'query': run.query,
        'answer': run.answer_text,
        'citations': run.citations,
        'evidence_count': run.evidence_count,
        'step_count': run.step_count,
        'error_code': run.error_code,
        'requested_mode': run.requested_mode,
        'attempts': run.attempts,
        'cancel_requested': run.cancel_requested,
        'metrics': metrics,
        'created_at': run.created_at.isoformat() if run.created_at else '',
        'created_at_label': timezone.localtime(run.created_at).strftime('%m-%d %H:%M') if run.created_at else '',
        'finished_at': run.finished_at.isoformat() if run.finished_at else '',
        'artifacts': artifacts,
        'skill_activations': activations,
        'worker': worker_status() if run.status in ACTIVE_STATUSES else {},
    }
    if include_steps:
        if staff:
            payload['steps'] = [
                {
                    'step_id': step.step_id, 'step_type': step.step_type, 'decision': step.decision,
                    'reason_code': step.reason_code, 'latency_ms': step.latency_ms,
                    'tokens': step.tokens, 'tool_calls': step.tool_calls,
                    'evidence_count': len(step.evidence_ids or []), 'failure_code': step.failure_code,
                }
                for step in run.steps.all()
            ]
        else:
            payload['steps'] = [
                {'step_id': step.step_id, 'step_type': step.step_type, 'decision': step.decision}
                for step in run.steps.all()
            ]
    if include_evidence:
        payload['evidence'] = [
            {
                'evidence_id': row.evidence_id, 'chunk_id': row.chunk_id, 'document_id': row.document_id,
                'page': row.page, 'heading_path': row.heading_path, 'content': row.content,
                'source_uri': row.source_uri, 'retrieval_score': row.retrieval_score,
                'authority_score': row.authority_score, 'content_hash': row.content_hash,
                'source_version': row.source_version,
            }
            for row in run.evidence.all().order_by('-retrieval_score')[:12]
        ]
    return payload
