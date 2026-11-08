"""Workspace document upload, soft removal and restore.

Parsing is synchronous for a single uploaded file so the UI can truthfully
report a terminal state. The stored file remains available for an explicit
retry; uploaded files are never executed.
"""

from pathlib import Path
import uuid

from django.conf import settings
from django.utils import timezone

from core.exceptions import BusinessError, ValidationError

from apps.knowledge.services.mime_router import route_for_path

from ..models import WorkspaceDocument
from ..permissions import ensure_writable
from .workspaces import serialize_document_link


ACTIVE_STATUSES = ('ready', 'partial')


def active_document_ids(workspace):
    return list(
        WorkspaceDocument.objects.filter(workspace=workspace, status__in=ACTIVE_STATUSES)
        .exclude(document__isnull=True)
        .values_list('document_id', flat=True)
    )


def scoped_document_hashes(workspace):
    from apps.knowledge.models import KnowledgeDocument
    ids = active_document_ids(workspace)
    return list(KnowledgeDocument.objects.filter(pk__in=ids).values_list('document_hash', flat=True))


def _safe_target(workspace, original_name):
    name = Path(str(original_name or '')).name
    if not name or name in ('.', '..'):
        raise ValidationError('文件名无效。')
    root = Path(getattr(settings, 'EVIDENCE_RAG_UPLOAD_DIR')) / 'workspaces' / str(workspace.pk)
    target_dir = root / uuid.uuid4().hex
    target_dir.mkdir(parents=True, exist_ok=False)
    return target_dir / name


def _store_upload(workspace, uploaded):
    max_bytes = getattr(settings, 'EVIDENCE_RAG_MAX_UPLOAD_BYTES', 20 * 1024 * 1024)
    if uploaded is None:
        raise ValidationError('请选择要上传的文件。')
    if uploaded.size <= 0:
        raise ValidationError('上传文件为空。')
    if uploaded.size > max_bytes:
        raise ValidationError(f'文件超过 {max_bytes // (1024 * 1024)} MB 限制。', code='FILE_TOO_LARGE')
    route_for_path(Path(uploaded.name))
    target = _safe_target(workspace, uploaded.name)
    with target.open('wb') as handle:
        for block in uploaded.chunks():
            handle.write(block)
    return target


def _ingest(link, workspace, path, annotation=''):
    from apps.knowledge.services.advanced_index_service import ingest_advanced

    try:
        outcome = ingest_advanced(path, annotation=annotation, rebuild=False, index=True, workspace=workspace)
    except BusinessError as exc:
        link.status = 'failed'
        link.error_message = exc.message
        link.save(update_fields=['status', 'error_message', 'updated_at'])
        raise
    except Exception as exc:
        link.status = 'failed'
        link.error_message = f'解析失败：{type(exc).__name__}'
        link.save(update_fields=['status', 'error_message', 'updated_at'])
        raise ValidationError('文件解析失败，请检查格式或重试。', code='DOCUMENT_PARSE_FAILED')

    document = outcome['document']
    warning = outcome.get('warning') or ''
    link.document = document
    link.original_name = document.name
    link.file_path = document.path
    if document.ingestion_status == 'failed':
        link.status = 'failed'
        link.error_message = warning or '索引失败。'
    elif warning or document.ingestion_status == 'partial':
        link.status = 'partial'
        link.error_message = warning or '向量索引不可用，已保留词法检索。'
    else:
        link.status = 'ready'
        link.error_message = ''
    link.save(update_fields=['document', 'original_name', 'file_path', 'status', 'error_message', 'updated_at'])
    return link


def upload_document(user, workspace, uploaded, annotation=''):
    ensure_writable(user, workspace)
    target = _store_upload(workspace, uploaded)
    link = WorkspaceDocument.objects.create(
        workspace=workspace,
        added_by=user,
        original_name=Path(target).name,
        file_path=str(target),
        status='processing',
    )
    try:
        return _ingest(link, workspace, target, annotation=annotation)
    finally:
        # The private upload copy is intentionally retained for retry; it is not public.
        pass


def retry_document(user, workspace, link):
    ensure_writable(user, workspace)
    if link.workspace_id != workspace.pk:
        raise ValidationError('资料不属于该工作空间。', code='DOCUMENT_WORKSPACE_MISMATCH')
    if link.status not in ('failed', 'partial'):
        raise ValidationError('只有失败或部分可用的资料需要重试。')
    path = Path(link.file_path or '')
    if not path.is_file():
        link.status = 'failed'
        link.error_message = '原始上传文件已不可用，请重新上传。'
        link.save(update_fields=['status', 'error_message', 'updated_at'])
        raise ValidationError('原始上传文件已不可用，请重新上传。', code='UPLOAD_FILE_MISSING')
    link.status = 'processing'
    link.error_message = ''
    link.save(update_fields=['status', 'error_message', 'updated_at'])
    return _ingest(link, workspace, path)


def remove_document(user, workspace, link):
    ensure_writable(user, workspace)
    if link.workspace_id != workspace.pk:
        raise ValidationError('资料不属于该工作空间。', code='DOCUMENT_WORKSPACE_MISMATCH')
    link.status = 'removed'
    link.removed_at = timezone.now()
    link.save(update_fields=['status', 'removed_at', 'updated_at'])
    return serialize_document_link(link)


def restore_document(user, workspace, link):
    ensure_writable(user, workspace)
    if link.workspace_id != workspace.pk:
        raise ValidationError('资料不属于该工作空间。', code='DOCUMENT_WORKSPACE_MISMATCH')
    if link.status != 'removed':
        raise ValidationError('只有已移除的资料可以恢复。')
    document = link.document
    if document is None:
        link.status = 'failed'
        link.error_message = '原文档不存在，请重新上传。'
    elif document.ingestion_status == 'ready':
        link.status = 'ready'
    elif document.ingestion_status in ('parsed', 'partial', 'legacy'):
        link.status = 'partial'
    else:
        link.status = 'failed'
    link.removed_at = None
    link.save(update_fields=['status', 'removed_at', 'error_message', 'updated_at'])
    return serialize_document_link(link)
