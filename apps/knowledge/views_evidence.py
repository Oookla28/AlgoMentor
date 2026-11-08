"""EvidenceRAG Studio APIs: tree, document maintenance, chunk CRUD, traces, conflicts, media."""

from pathlib import Path
import hashlib
import uuid

from django.conf import settings
from django.db import transaction
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone

from core.exceptions import BusinessError, KnowledgeRetrievalError, ValidationError
from core.http import api_endpoint, json_body
from core.security.permissions import require_user

from .models import KnowledgeChunk, KnowledgeConflict, KnowledgeDocument, KnowledgeQueryTrace, MediaAsset
from .services.evidence_schema import evidence_from_chunk, evidence_from_media
from .services.hierarchical_chunker import estimate_tokens


def _require_staff(user):
    require_user(user)
    if not user.is_staff:
        raise BusinessError('该维护操作仅限管理员。', code='PERMISSION_DENIED', status_code=403)


def _require_trace_access(user, trace):
    require_user(user)
    if user.is_staff or trace.user_id == user.id:
        return
    raise BusinessError('无权查看该检索轨迹。', code='PERMISSION_DENIED', status_code=403)


def _serialize_chunk(chunk, include_content=True, include_children=False):
    payload = {
        'chunk_id': chunk.chunk_id,
        'document_id': chunk.document_id,
        'document_name': chunk.document.name,
        'chapter': chunk.chapter,
        'section': chunk.section,
        'page_number': chunk.page_number,
        'chunk_type': chunk.chunk_type,
        'parent_chunk_id': chunk.parent_chunk.chunk_id if chunk.parent_chunk_id else '',
        'heading_path': chunk.heading_path,
        'char_start': chunk.char_start,
        'char_end': chunk.char_end,
        'token_count': chunk.token_count,
        'overlap_start': chunk.overlap_start,
        'overlap_end': chunk.overlap_end,
        'parser_confidence': chunk.parser_confidence,
        'content_hash': chunk.content_hash,
        'is_active': chunk.is_active,
        'deleted_at': chunk.deleted_at.isoformat() if chunk.deleted_at else '',
        'source_type': chunk.source_type,
        'version': chunk.version,
        'media_asset_id': chunk.media_asset.asset_id if chunk.media_asset_id else '',
    }
    if include_content:
        payload['content'] = chunk.content
    if include_children:
        payload['children'] = [
            _serialize_chunk(child, include_content=False)
            for child in chunk.children.filter(is_active=True).order_by('chunk_id')[:getattr(settings, 'EVIDENCE_RAG_TREE_PAGE_SIZE', 50)]
        ]
    return payload


def _serialize_document(document, include_tree=True):
    parents = list(document.chunks.filter(chunk_type='parent', is_active=True).order_by('chunk_id')[:getattr(settings, 'EVIDENCE_RAG_TREE_PAGE_SIZE', 50)])
    parent_ids = [parent.pk for parent in parents]
    children = list(
        document.chunks.filter(chunk_type='child', is_active=True, parent_chunk_id__in=parent_ids).order_by('chunk_id')
        if parent_ids else []
    )
    grouped = {}
    for child in children:
        grouped.setdefault(child.parent_chunk_id, []).append(child)
    media = list(document.media_assets.all()[:20])
    child_count = document.chunks.filter(chunk_type='child', is_active=True).count()
    parent_count = document.chunks.filter(chunk_type='parent', is_active=True).count()
    payload = {
        'id': document.pk,
        'name': document.name,
        'document_hash': document.document_hash,
        'source_type': document.source_type,
        'authority_level': document.authority_level,
        'page_count': document.page_count,
        'version': document.version,
        'parser_name': document.parser_name,
        'parser_version': document.parser_version,
        'ingestion_status': document.ingestion_status,
        'index_version': document.index_version,
        'advanced_index_version': document.latest_index_version,
        'embedding_model': document.embedding_model,
        'embedding_dimension': document.embedding_dimension,
        'created_at': document.created_at.isoformat() if document.created_at else '',
        'valid_from': document.valid_from.isoformat() if document.valid_from else '',
        'valid_to': document.valid_to.isoformat() if document.valid_to else '',
        'parent_count': parent_count,
        'child_count': child_count,
        'media_count': document.media_assets.count(),
        'metadata': document.source_metadata,
    }
    if include_tree:
        payload['parents'] = [
            {
                **_serialize_chunk(parent, include_content=False),
                'children': [_serialize_chunk(child, include_content=False) for child in grouped.get(parent.pk, [])[:getattr(settings, 'EVIDENCE_RAG_TREE_PAGE_SIZE', 50)]],
            }
            for parent in parents
        ]
        payload['media'] = [evidence_from_media(asset).to_dict() for asset in media]
        payload['truncated'] = parent_count > len(parents) or child_count > len(children)
    return payload


@api_endpoint()
def tree(request):
    documents = KnowledgeDocument.objects.order_by('-created_at')[:20]
    return {'documents': [_serialize_document(document) for document in documents]}


@api_endpoint()
def document_detail(request, document_id):
    document = get_object_or_404(KnowledgeDocument, pk=document_id)
    return _serialize_document(document)


def _safe_upload_path(name: str) -> Path:
    original = Path(str(name or '')).name
    if not original or original in ('.', '..'):
        raise ValidationError('文件名无效。')
    target_dir = Path(settings.EVIDENCE_RAG_UPLOAD_DIR) / uuid.uuid4().hex
    target_dir.mkdir(parents=True, exist_ok=False)
    return target_dir / original


@api_endpoint(methods=('POST',))
def upload_document(request):
    _require_staff(request.user)
    uploaded = request.FILES.get('file')
    if uploaded is None:
        raise ValidationError('请选择要上传的文件。')
    if uploaded.size <= 0:
        raise ValidationError('上传文件为空。')
    max_bytes = getattr(settings, 'EVIDENCE_RAG_MAX_UPLOAD_BYTES', 20 * 1024 * 1024)
    if uploaded.size > max_bytes:
        raise ValidationError(f'文件超过 {max_bytes // (1024 * 1024)} MB 限制。', code='FILE_TOO_LARGE')
    from .services.mime_router import route_for_path
    route_for_path(Path(uploaded.name))
    target = _safe_upload_path(uploaded.name)
    with target.open('wb') as handle:
        for block in uploaded.chunks():
            handle.write(block)
    annotation = (request.POST.get('annotation') or '').strip()[:20000]
    caption = (request.POST.get('caption') or '').strip()[:2000]
    from .services.advanced_index_service import ingest_advanced
    try:
        outcome = ingest_advanced(target, annotation=annotation, caption=caption, rebuild=True, index=True)
    except Exception:
        try:
            target.unlink()
        except OSError:
            pass
        raise
    document = outcome['document']
    return {
        'document': _serialize_document(document, include_tree=False),
        'parsed': outcome['parsed'],
        'index': outcome['index'],
        'warning': outcome['warning'],
        'status': document.ingestion_status,
    }


@api_endpoint(methods=('POST',))
def reindex_document_api(request, document_id):
    _require_staff(request.user)
    document = get_object_or_404(KnowledgeDocument, pk=document_id)
    body = json_body(request)
    mode = str(body.get('mode', 'advanced')).lower()
    rebuild = bool(body.get('rebuild', True))
    if mode not in ('advanced', 'legacy', 'both'):
        raise ValidationError('重建模式仅支持 advanced、legacy 或 both。')
    results = {}
    if mode == 'legacy':
        if document.source_type != 'pdf':
            raise ValidationError('旧版索引只支持 PDF。', code='LEGACY_PDF_ONLY')
        from django.core.management import call_command
        path = Path(document.path)
        if not path.is_absolute():
            path = Path(settings.BASE_DIR) / path
        if not path.is_file():
            raise ValidationError('原始文件不存在，无法重建旧版索引。', code='SOURCE_FILE_MISSING')
        call_command('ingest_knowledge', path=str(path), rebuild=rebuild, verbosity=0)
        results['legacy'] = 'reindexed'
    elif mode == 'advanced':
        from .services.advanced_index_service import ingest_advanced, reindex_document
        if not document.chunks.filter(chunk_type__in=['child', 'media']).exists():
            path = Path(document.path)
            if not path.is_absolute():
                path = Path(settings.BASE_DIR) / path
            if not path.is_file():
                raise ValidationError('原始文件不存在，无法解析。', code='SOURCE_FILE_MISSING')
            results['advanced'] = ingest_advanced(path, rebuild=True, index=True)['index']
        else:
            results['advanced'] = reindex_document(document, rebuild=rebuild)
    else:
        if document.source_type != 'pdf':
            raise ValidationError('both 模式目前只支持 PDF。', code='LEGACY_PDF_ONLY')
        from django.core.management import call_command
        from .services.advanced_index_service import reindex_document
        path = Path(document.path)
        if not path.is_absolute():
            path = Path(settings.BASE_DIR) / path
        call_command('ingest_knowledge', path=str(path), rebuild=rebuild, verbosity=0)
        results['legacy'] = 'reindexed'
        results['advanced'] = reindex_document(document, rebuild=rebuild)
    document.refresh_from_db()
    return {'document': _serialize_document(document, include_tree=False), 'results': results}


@api_endpoint()
def chunk_detail(request, chunk_id):
    chunk = get_object_or_404(KnowledgeChunk.objects.select_related('document', 'parent_chunk', 'media_asset'), chunk_id=chunk_id)
    payload = _serialize_chunk(chunk, include_children=True)
    payload['evidence'] = evidence_from_chunk(chunk).to_dict()
    payload['claims'] = [
        {
            'claim_id': claim.claim_id,
            'subject': claim.subject,
            'predicate': claim.predicate,
            'object': claim.object,
            'normalized_text': claim.normalized_text,
            'authority_level': claim.authority_level,
        }
        for claim in chunk.claims.all()[:20]
    ]
    payload['media'] = evidence_from_media(chunk.media_asset).to_dict() if chunk.media_asset_id else None
    return payload


@api_endpoint(methods=('PATCH',))
def chunk_patch(request, chunk_id):
    _require_staff(request.user)
    chunk = get_object_or_404(KnowledgeChunk.objects.select_related('document', 'parent_chunk', 'media_asset'), chunk_id=chunk_id)
    body = json_body(request)
    content = body.get('content')
    if content is not None:
        if not isinstance(content, str) or not content.strip() or len(content) > 20000:
            raise ValidationError('片段内容须为 1 至 20000 字。')
    heading_path = body.get('heading_path')
    if heading_path is not None and (not isinstance(heading_path, str) or len(heading_path) > 500):
        raise ValidationError('标题路径过长。')
    parent_chunk_id = body.get('parent_chunk_id')
    new_parent = None
    if parent_chunk_id is not None:
        if chunk.chunk_type != 'child':
            raise ValidationError('只有子块可以修改父块关系。', code='INVALID_PARENT_CHANGE')
        if parent_chunk_id:
            new_parent = KnowledgeChunk.objects.filter(
                chunk_id=str(parent_chunk_id), document=chunk.document, chunk_type='parent',
            ).first()
            if new_parent is None:
                raise ValidationError('父块不存在或不属于当前文档。', code='PARENT_NOT_FOUND')
            ancestor = new_parent
            while ancestor is not None:
                if ancestor.pk == chunk.pk:
                    raise ValidationError('父子关系不能形成环。', code='PARENT_CYCLE')
                ancestor = ancestor.parent_chunk
        else:
            new_parent = None
    old = {
        'content': chunk.content,
        'heading_path': chunk.heading_path,
        'content_hash': chunk.content_hash,
        'token_count': chunk.token_count,
        'parent_chunk': chunk.parent_chunk,
    }
    with transaction.atomic():
        if content is not None:
            chunk.content = content.strip()
            chunk.content_hash = hashlib.sha256(chunk.content.encode('utf-8')).hexdigest()
            chunk.token_count = estimate_tokens(chunk.content)
        if heading_path is not None:
            chunk.heading_path = heading_path.strip()
        if parent_chunk_id is not None:
            chunk.parent_chunk = new_parent
        chunk.save(update_fields=['content', 'heading_path', 'content_hash', 'token_count', 'parent_chunk'])
        if content is not None and chunk.document.latest_index_version and chunk.chunk_type in ('child', 'media'):
            from .services.advanced_index_service import upsert_chunk_vector
            ok, reason = upsert_chunk_vector(chunk.document, chunk)
            if not ok:
                chunk.content = old['content']
                chunk.heading_path = old['heading_path']
                chunk.content_hash = old['content_hash']
                chunk.token_count = old['token_count']
                chunk.parent_chunk = old['parent_chunk']
                chunk.save(update_fields=['content', 'heading_path', 'content_hash', 'token_count', 'parent_chunk'])
                upsert_chunk_vector(chunk.document, chunk)
                raise KnowledgeRetrievalError('向量索引更新失败，数据库改动已回滚。', code='INDEX_SYNC_FAILED')
    chunk.refresh_from_db()
    return _serialize_chunk(chunk, include_children=True)


def chunk_dispatch(request, chunk_id):
    """Route one URL to GET/PATCH/DELETE handlers; each handler keeps its own guard."""
    if request.method == 'GET':
        return chunk_detail(request, chunk_id)
    if request.method == 'PATCH':
        return chunk_patch(request, chunk_id)
    if request.method == 'DELETE':
        return chunk_delete(request, chunk_id)
    from django.http import HttpResponseNotAllowed
    return HttpResponseNotAllowed(['GET', 'PATCH', 'DELETE'])


@api_endpoint(methods=('DELETE',))
def chunk_delete(request, chunk_id):
    _require_staff(request.user)
    chunk = get_object_or_404(KnowledgeChunk.objects.select_related('document'), chunk_id=chunk_id)
    vector_removed = False
    try:
        with transaction.atomic():
            if chunk.document.latest_index_version and chunk.chunk_type in ('child', 'media'):
                from .services.advanced_index_service import remove_vectors
                ok, reason = remove_vectors(chunk.document.latest_index_version, [chunk.chunk_id])
                if not ok:
                    raise KnowledgeRetrievalError('向量索引删除失败，片段未删除。', code='INDEX_SYNC_FAILED')
                vector_removed = True
            chunk.is_active = False
            chunk.deleted_at = timezone.now()
            chunk.save(update_fields=['is_active', 'deleted_at'])
    except Exception:
        if vector_removed:
            from .services.advanced_index_service import upsert_chunk_vector
            upsert_chunk_vector(chunk.document, chunk)
        raise
    return {'chunk_id': chunk.chunk_id, 'is_active': False, 'deleted_at': chunk.deleted_at.isoformat()}


@api_endpoint(methods=('POST',))
def chunk_restore(request, chunk_id):
    _require_staff(request.user)
    chunk = get_object_or_404(KnowledgeChunk.objects.select_related('document', 'parent_chunk', 'media_asset'), chunk_id=chunk_id)
    with transaction.atomic():
        chunk.is_active = True
        chunk.deleted_at = None
        chunk.save(update_fields=['is_active', 'deleted_at'])
        if chunk.document.latest_index_version and chunk.chunk_type in ('child', 'media'):
            from .services.advanced_index_service import upsert_chunk_vector
            ok, reason = upsert_chunk_vector(chunk.document, chunk)
            if not ok:
                chunk.is_active = False
                chunk.deleted_at = timezone.now()
                chunk.save(update_fields=['is_active', 'deleted_at'])
                raise KnowledgeRetrievalError('向量索引恢复失败，片段仍保持删除状态。', code='INDEX_SYNC_FAILED')
    chunk.refresh_from_db()
    return _serialize_chunk(chunk, include_children=True)


@api_endpoint()
def trace_detail(request, trace_id):
    trace = get_object_or_404(KnowledgeQueryTrace, trace_id=trace_id)
    _require_trace_access(request.user, trace)
    from .services.conflict_service import serialize_conflict
    from .services.trace_service import serialize_trace
    payload = serialize_trace(trace)
    payload['conflicts'] = [serialize_conflict(conflict) for conflict in trace.conflicts.select_related('claim_a__source_chunk', 'claim_b__source_chunk')[:20]]
    return payload


@api_endpoint()
def conflict_detail(request, conflict_id):
    conflict = get_object_or_404(KnowledgeConflict.objects.select_related('claim_a__source_chunk', 'claim_b__source_chunk'), conflict_id=conflict_id)
    if conflict.query_trace_id:
        _require_trace_access(request.user, conflict.query_trace)
    else:
        require_user(request.user)
    from .services.conflict_service import serialize_conflict
    return serialize_conflict(conflict)


@api_endpoint()
def media_file(request, asset_id):
    require_user(request.user)
    asset = get_object_or_404(MediaAsset, asset_id=asset_id)
    path = Path(asset.file_path)
    if not path.is_absolute():
        path = Path(settings.BASE_DIR) / path
    try:
        resolved = path.resolve()
        roots = [Path(settings.BASE_DIR).resolve(), Path(settings.EVIDENCE_RAG_UPLOAD_DIR).resolve()]
        allowed = False
        for root in roots:
            try:
                resolved.relative_to(root)
                allowed = True
                break
            except ValueError:
                continue
        if not allowed:
            raise ValueError('outside allowed root')
    except Exception:
        raise BusinessError('媒体文件不可访问。', code='MEDIA_NOT_AVAILABLE', status_code=404)
    if not resolved.is_file():
        raise BusinessError('媒体文件不存在。', code='MEDIA_NOT_AVAILABLE', status_code=404)
    return FileResponse(resolved.open('rb'), content_type=asset.mime_type or 'application/octet-stream')
