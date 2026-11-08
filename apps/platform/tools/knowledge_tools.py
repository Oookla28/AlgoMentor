"""Read-only knowledge tools used by the explicit agent state machine."""

from dataclasses import asdict

from core.exceptions import BusinessError, ValidationError


def _payload(row):
    media = row.media_asset if row.media_asset_id else None
    return {
        'chunk_id': row.chunk_id,
        'document_id': row.document_id,
        'document_name': row.document.name,
        'document_hash': row.document.document_hash,
        'chapter': row.chapter,
        'section': row.section,
        'page': row.page_number,
        'chunk_type': row.chunk_type,
        'heading_path': row.heading_path,
        'content': row.content,
        'char_start': row.char_start,
        'char_end': row.char_end,
        'content_hash': row.content_hash,
        'source_version': row.version,
        'authority_level': row.document.authority_level,
        'valid_from': row.document.valid_from.isoformat() if row.document.valid_from else '',
        'valid_to': row.document.valid_to.isoformat() if row.document.valid_to else '',
        'source_type': row.source_type,
        'parent_chunk_id': row.parent_chunk.chunk_id if row.parent_chunk_id else '',
        'media_asset_id': media.asset_id if media else '',
        'start_time': media.start_time if media else None,
        'end_time': media.end_time if media else None,
        'modality': media.modality if media else 'text',
    }


def keyword_search(user, query: str, top_k: int = 10):
    from apps.knowledge.models import KnowledgeChunk
    from apps.knowledge.services.sparse_retrieval import sparse_search
    hits = sparse_search(query, top_k=max(1, min(int(top_k or 10), 30)))
    ids = [hit.chunk_id for hit in hits]
    rows = {row.chunk_id: row for row in KnowledgeChunk.objects.select_related('document', 'parent_chunk', 'media_asset').filter(chunk_id__in=ids, is_active=True)}
    results = []
    for hit in hits:
        row = rows.get(hit.chunk_id)
        if row is None:
            continue
        results.append({**_payload(row), 'retrieval_score': hit.score, 'rank': hit.rank, 'retriever': 'bm25'})
    return {'results': results, 'query': query, 'retriever': 'bm25', 'count': len(results)}


def semantic_search(user, query: str, top_k: int = 10):
    from apps.knowledge.models import KnowledgeChunk
    from apps.knowledge.services.retrieval_service import retrieve_knowledge
    citations = retrieve_knowledge(query, top_k=max(1, min(int(top_k or 10), 8)))
    ids = [citation.chunk_id for citation in citations]
    rows = {row.chunk_id: row for row in KnowledgeChunk.objects.select_related('document', 'parent_chunk', 'media_asset').filter(chunk_id__in=ids)}
    results = []
    for rank, citation in enumerate(citations, 1):
        row = rows.get(citation.chunk_id)
        if row is None:
            continue
        results.append({**_payload(row), 'retrieval_score': citation.score, 'rank': rank, 'retriever': 'dense'})
    return {'results': results, 'query': query, 'retriever': 'dense', 'count': len(results)}


def _get_chunk(chunk_id: str):
    from apps.knowledge.models import KnowledgeChunk
    chunk = KnowledgeChunk.objects.select_related('document', 'parent_chunk', 'media_asset').filter(chunk_id=str(chunk_id), is_active=True).first()
    if chunk is None:
        raise ValidationError('证据片段不存在或已删除。', code='EVIDENCE_NOT_FOUND')
    return chunk


def read_child(user, chunk_id: str):
    return {'result': _payload(_get_chunk(chunk_id))}


def read_parent(user, chunk_id: str):
    chunk = _get_chunk(chunk_id)
    parent = chunk.parent_chunk
    if parent is None:
        return {'result': _payload(chunk), 'note': 'NO_PARENT'}
    return {'result': _payload(parent)}


def read_siblings(user, chunk_id: str, limit: int = 4):
    chunk = _get_chunk(chunk_id)
    parent = chunk.parent_chunk
    if parent is None:
        return {'results': [], 'note': 'NO_PARENT'}
    siblings = parent.children.filter(is_active=True).exclude(pk=chunk.pk).order_by('chunk_id')[:max(1, min(int(limit or 4), 8))]
    return {'results': [_payload(row) for row in siblings]}


def read_source_page(user, chunk_id: str, limit: int = 6):
    chunk = _get_chunk(chunk_id)
    rows = chunk.document.chunks.filter(page_number=chunk.page_number, is_active=True).order_by('chunk_id')[:max(1, min(int(limit or 6), 12))]
    return {'results': [_payload(row) for row in rows]}


def retrieve_conflicting_versions(user, query: str, chunk_id: str = '', top_k: int = 5):
    from apps.knowledge.models import KnowledgeChunk
    from apps.knowledge.services.sparse_retrieval import sparse_search
    chunk = _get_chunk(chunk_id) if chunk_id else None
    if chunk is None:
        return {'results': [], 'note': 'NO_REFERENCE_CHUNK'}
    versions = chunk.document.__class__.objects.filter(name=chunk.document.name).exclude(pk=chunk.document_id)
    version_ids = list(versions.values_list('pk', flat=True))
    if not version_ids:
        return {'results': [], 'note': 'NO_OTHER_VERSIONS'}
    rows = list(KnowledgeChunk.objects.filter(document_id__in=version_ids, is_active=True).values_list('chunk_id', 'content'))
    hits = sparse_search(query, documents=rows, top_k=max(1, min(int(top_k or 5), 10)))
    by_id = {row.chunk_id: row for row in KnowledgeChunk.objects.select_related('document', 'parent_chunk', 'media_asset').filter(chunk_id__in=[hit.chunk_id for hit in hits])}
    return {'results': [{**_payload(by_id[hit.chunk_id]), 'retrieval_score': hit.score, 'rank': hit.rank} for hit in hits if hit.chunk_id in by_id]}
