"""Advanced hierarchical indexing: parent/child chunks plus an independent Chroma collection."""

import hashlib
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from langchain_core.documents import Document

from core.exceptions import KnowledgeRetrievalError

from .embedding_service import build_embeddings, cached_embeddings, embedding_identity
from .hierarchical_chunker import chunk_document, estimate_tokens
from .multimodal_loader import ParsedDocument, load_any


def advanced_index_version() -> str:
    identity = embedding_identity()
    label = getattr(settings, 'EVIDENCE_RAG_INDEX_VERSION', 'adv-v1')
    digest = hashlib.sha256(f'{identity}|{label}|hierarchical-v1'.encode('utf-8')).hexdigest()[:24]
    return f'adv-{digest}'


def collection_name_for(index_version: str) -> str:
    return f'ev-{index_version}'[:63]


def _relative(path: Path) -> str:
    try:
        return str(Path(path).resolve().relative_to(Path(settings.BASE_DIR).resolve()))
    except ValueError:
        return str(Path(path).resolve())[:500]


def _chunk_defaults(document, chunk):
    return {
        'document': document,
        'chapter': chunk.chapter,
        'section': chunk.section,
        'page_number': chunk.page_number,
        'content': chunk.content,
        'source_type': document.source_type,
        'version': document.version,
        'chunk_type': chunk.chunk_type,
        'heading_path': chunk.heading_path,
        'char_start': chunk.char_start,
        'char_end': chunk.char_end,
        'token_count': chunk.token_count,
        'overlap_start': chunk.overlap_start,
        'overlap_end': chunk.overlap_end,
        'parser_confidence': chunk.parser_confidence,
        'content_hash': chunk.content_hash,
        'is_active': True,
        'deleted_at': None,
    }


def _store_media(document, parsed: ParsedDocument):
    from apps.knowledge.models import KnowledgeChunk, MediaAsset
    children = []
    for probe in parsed.media:
        asset, _created = MediaAsset.objects.update_or_create(
            asset_id=probe.asset_id,
            defaults={
                'document': document,
                'modality': probe.modality,
                'file_path': _relative(Path(probe.file_path)),
                'mime_type': probe.mime_type,
                'sha256': probe.sha256,
                'ocr_text': probe.ocr_text,
                'asr_text': probe.asr_text,
                'caption': probe.caption,
                'manual_annotation': probe.manual_annotation,
                'parser_confidence': probe.parser_confidence,
                'metadata': probe.metadata,
            },
        )
        content = probe.manual_annotation or probe.caption or probe.ocr_text or probe.asr_text or f'{probe.modality} 证据：{Path(probe.file_path).name}'
        chunk_id = f'media-{probe.asset_id}'[:100]
        chunk, _created = KnowledgeChunk.objects.update_or_create(
            chunk_id=chunk_id,
            defaults={
                'document': document,
                'chapter': document.name[:100],
                'section': '媒体证据',
                'page_number': 1,
                'content': content,
                'source_type': document.source_type,
                'version': document.version,
                'chunk_type': 'media',
                'heading_path': document.name[:500],
                'char_start': 0,
                'char_end': len(content),
                'token_count': estimate_tokens(content),
                'parser_confidence': probe.parser_confidence,
                'content_hash': hashlib.sha256(content.encode('utf-8')).hexdigest(),
                'media_asset': asset,
                'is_active': True,
                'deleted_at': None,
            },
        )
        children.append(chunk)
    return children


def parse_and_store_advanced(document, parsed: ParsedDocument):
    """Create parent/child (or media) chunks for a parsed document. Legacy chunks are untouched."""
    from apps.knowledge.models import KnowledgeChunk
    result = None
    with transaction.atomic():
        if parsed.media:
            children = _store_media(document, parsed)
            parents = []
            chunk_ids = [chunk.chunk_id for chunk in children]
        else:
            result = chunk_document(parsed.document)
            parent_rows = {}
            parents = []
            for parent in result.parents:
                row, _created = KnowledgeChunk.objects.update_or_create(
                    chunk_id=parent.chunk_id,
                    defaults=_chunk_defaults(document, parent),
                )
                parent_rows[parent.chunk_id] = row
                parents.append(row)
            children = []
            for child in result.children:
                defaults = _chunk_defaults(document, child)
                defaults['parent_chunk'] = parent_rows.get(child.parent_chunk_id)
                row, _created = KnowledgeChunk.objects.update_or_create(chunk_id=child.chunk_id, defaults=defaults)
                children.append(row)
            chunk_ids = [row.chunk_id for row in parents + children]
        stale = document.chunks.filter(chunk_type__in=['parent', 'child', 'media']).exclude(chunk_id__in=chunk_ids)
        stale_ids = list(stale.values_list('chunk_id', flat=True))
        stale.delete()
        document.source_type = parsed.source_type
        document.parser_name = parsed.parser_name
        document.parser_version = parsed.parser_version
        document.page_count = len(parsed.document.pages)
        document.ingestion_status = 'parsed'
        document.latest_index_version = ''
        document.source_metadata = {
            **(document.source_metadata or {}),
            'advanced': {
                'structure_confidence': getattr(result, 'structure_confidence', 0.0) if not parsed.media else 1.0,
                'has_headings': getattr(result, 'has_headings', False) if not parsed.media else False,
                'warnings': list(parsed.warnings),
                'modalities': [probe.modality for probe in parsed.media],
                'stale_vector_ids': stale_ids,
            },
            **parsed.metadata,
        }
        document.save(update_fields=['source_type', 'parser_name', 'parser_version', 'page_count', 'ingestion_status', 'latest_index_version', 'source_metadata'])
    return {
        'parents': len(parents),
        'children': len(children),
        'stale_chunks': len(stale_ids),
        'stale_chunk_ids': stale_ids,
        'structure_confidence': getattr(result, 'structure_confidence', 0.0) if not parsed.media else 1.0,
        'has_headings': getattr(result, 'has_headings', False) if not parsed.media else False,
        'warnings': list(parsed.warnings),
    }


def _vector_metadata(document, chunk) -> dict:
    return {
        'chunk_id': chunk.chunk_id,
        'parent_chunk_id': chunk.parent_chunk.chunk_id if chunk.parent_chunk_id else '',
        'document_hash': document.document_hash,
        'document_name': document.name,
        'chapter': chunk.chapter,
        'section': chunk.section,
        'page_number': chunk.page_number,
        'heading_path': chunk.heading_path,
        'char_start': chunk.char_start or 0,
        'char_end': chunk.char_end or 0,
        'source_type': chunk.source_type,
        'version': chunk.version,
        'chunk_type': chunk.chunk_type,
        'authority_level': document.authority_level,
        'content_hash': chunk.content_hash,
    }


def index_advanced_chunks(document, rebuild: bool = False) -> dict:
    from langchain_chroma import Chroma
    from apps.knowledge.models import KnowledgeChunk
    chunks = list(
        KnowledgeChunk.objects.filter(document=document, chunk_type__in=['child', 'media'], is_active=True)
        .select_related('parent_chunk').order_by('page_number', 'chunk_id')
    )
    if not chunks:
        raise KnowledgeRetrievalError('没有可索引的子块，请先解析文档。', code='ADVANCED_INDEX_EMPTY')
    index_version = advanced_index_version()
    collection_name = collection_name_for(index_version)
    texts = [chunk.content for chunk in chunks]
    embedding = build_embeddings(index_version, texts)
    dimension = len(embedding.embed_query('数据结构'))
    store = Chroma(
        collection_name=collection_name,
        persist_directory=str(settings.CHROMA_PATH),
        embedding_function=embedding,
        collection_metadata={'hnsw:space': 'cosine'},
    )
    if rebuild:
        try:
            store.delete_collection()
        except Exception:
            pass
        store = Chroma(
            collection_name=collection_name,
            persist_directory=str(settings.CHROMA_PATH),
            embedding_function=embedding,
            collection_metadata={'hnsw:space': 'cosine'},
        )
    documents = [
        Document(page_content=chunk.content, metadata=_vector_metadata(document, chunk))
        for chunk in chunks
    ]
    store.add_documents(documents, ids=[chunk.chunk_id for chunk in chunks])
    try:
        count = store._collection.count()
    except Exception:
        count = len(chunks)
    if count != len(chunks):
        raise KnowledgeRetrievalError('高级向量索引数量与数据库不一致。', code='ADVANCED_INDEX_COUNT_MISMATCH')
    document.latest_index_version = index_version
    document.ingestion_status = 'ready'
    document.source_metadata = {
        **(document.source_metadata or {}),
        'advanced': {
            **((document.source_metadata or {}).get('advanced') or {}),
            'index_version': index_version,
            'collection_name': collection_name,
            'embedding_identity': embedding_identity(),
            'embedding_dimension': dimension,
            'indexed_chunks': len(chunks),
            'indexed_at': timezone.now().isoformat(),
        },
    }
    document.save(update_fields=['latest_index_version', 'ingestion_status', 'source_metadata'])
    cached_embeddings.cache_clear()
    return {
        'index_version': index_version,
        'collection_name': collection_name,
        'embedding_identity': embedding_identity(),
        'embedding_dimension': dimension,
        'indexed_chunks': len(chunks),
    }


def ingest_advanced(path, annotation: str = '', caption: str = '', rebuild: bool = True, index: bool = True):
    from apps.knowledge.models import KnowledgeDocument
    path = Path(path)
    parsed = load_any(path, annotation=annotation, caption=caption)
    existing = KnowledgeDocument.objects.filter(document_hash=parsed.document.document_hash).first()
    if existing is None:
        document = KnowledgeDocument.objects.create(
            name=parsed.document.name,
            document_hash=parsed.document.document_hash,
            path=_relative(path),
            version='1',
            page_count=len(parsed.document.pages),
            embedding_model=embedding_identity(),
            embedding_revision=getattr(settings, 'EMBEDDING_REVISION', ''),
            embedding_dimension=0,
            index_version='',
            collection_name='',
            source_type=parsed.source_type,
            parser_name=parsed.parser_name,
            parser_version=parsed.parser_version,
            ingestion_status='parsed',
            source_metadata={},
        )
    else:
        document = existing
    parsed_counts = parse_and_store_advanced(document, parsed)
    index_info = {}
    warning = ''
    if index:
        try:
            index_info = index_advanced_chunks(document, rebuild=rebuild)
        except Exception as exc:
            document.ingestion_status = 'partial'
            document.source_metadata = {
                **(document.source_metadata or {}),
                'advanced': {
                    **((document.source_metadata or {}).get('advanced') or {}),
                    'index_error': getattr(exc, 'code', type(exc).__name__),
                },
            }
            document.save(update_fields=['ingestion_status', 'source_metadata'])
            warning = getattr(exc, 'message', str(exc))
    return {'document': document, 'parsed': parsed_counts, 'index': index_info, 'warning': warning}


def reindex_document(document, rebuild: bool = True) -> dict:
    return index_advanced_chunks(document, rebuild=rebuild)


def remove_vectors(index_version: str, chunk_ids) -> tuple[bool, str]:
    if not index_version or not chunk_ids:
        return True, ''
    try:
        import chromadb
        client = chromadb.PersistentClient(path=str(settings.CHROMA_PATH))
        try:
            collection = client.get_collection(name=collection_name_for(index_version))
        except Exception as exc:
            if type(exc).__name__ in ('NotFoundError', 'ValueError'):
                return True, ''
            return False, type(exc).__name__
        collection.delete(ids=list(chunk_ids))
        return True, ''
    except Exception as exc:
        return False, type(exc).__name__


def delete_collection(index_version: str) -> tuple[bool, str]:
    if not index_version:
        return True, ''
    try:
        import chromadb
        client = chromadb.PersistentClient(path=str(settings.CHROMA_PATH))
        client.delete_collection(name=collection_name_for(index_version))
        return True, ''
    except Exception as exc:
        if type(exc).__name__ in ('ValueError', 'NotFoundError'):
            return True, ''
        return False, type(exc).__name__


def upsert_chunk_vector(document, chunk) -> tuple[bool, str]:
    if not document.latest_index_version:
        return True, ''
    from langchain_chroma import Chroma
    try:
        embedding = cached_embeddings(document.latest_index_version)
        store = Chroma(
            collection_name=collection_name_for(document.latest_index_version),
            persist_directory=str(settings.CHROMA_PATH),
            embedding_function=embedding,
            collection_metadata={'hnsw:space': 'cosine'},
        )
        try:
            store._collection.delete(ids=[chunk.chunk_id])
        except Exception:
            pass
        store.add_documents([Document(page_content=chunk.content, metadata=_vector_metadata(document, chunk))], ids=[chunk.chunk_id])
        return True, ''
    except Exception as exc:
        return False, type(exc).__name__
