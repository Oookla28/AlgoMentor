import hashlib

import pytest

from apps.knowledge.models import KnowledgeChunk, KnowledgeDocument
from apps.knowledge.services.hierarchical_chunker import estimate_tokens
from apps.knowledge.services.retrieval_service import Citation
from apps.knowledge.services.small2big_service import build_context, expand_citations


def _document():
    return KnowledgeDocument.objects.create(
        name='demo.pdf', document_hash=hashlib.sha256(b'demo').hexdigest(), path='demo.pdf',
        page_count=1, embedding_model='tfidf:char-1-3:2048:v1', embedding_revision='v1',
        embedding_dimension=8, index_version='idx', collection_name='course-idx',
        source_type='pdf', authority_level=1, ingestion_status='ready', latest_index_version='adv-demo',
    )


@pytest.mark.django_db
def test_context_contains_parent_hit_and_siblings():
    document = _document()
    parent = KnowledgeChunk.objects.create(
        document=document, chunk_id='p1', chapter='第一章', section='队列', page_number=3,
        content='父块完整上下文，介绍循环队列的队头、队尾、判空与判满。' * 20,
        chunk_type='parent', heading_path='第三章 > 队列', token_count=400,
        char_start=0, char_end=400, content_hash='a' * 64,
    )
    first = KnowledgeChunk.objects.create(
        document=document, chunk_id='c1', chapter='第三章', section='队列', page_number=3,
        content='循环队列判满条件是 (rear+1)%maxsize == front。', chunk_type='child',
        parent_chunk=parent, heading_path='第三章 > 队列', token_count=30,
    )
    second = KnowledgeChunk.objects.create(
        document=document, chunk_id='c2', chapter='第三章', section='队列', page_number=3,
        content='循环队列判空条件是 rear == front。', chunk_type='child',
        parent_chunk=parent, heading_path='第三章 > 队列', token_count=20,
    )
    window = build_context(first, budget_tokens=500)
    assert '父块' in window['context']
    assert '循环队列判满条件' in window['context']
    assert second.content in window['context'] or '判空条件' in window['context']
    assert window['parent_chunk_id'] == 'p1'
    assert window['heading_path'] == '第三章 > 队列'


@pytest.mark.django_db
def test_context_respects_token_budget():
    document = _document()
    parent = KnowledgeChunk.objects.create(
        document=document, chunk_id='p1', chapter='第一章', section='长文', page_number=1,
        content='很长的父块内容。' * 5000, chunk_type='parent', heading_path='第一章',
    )
    child = KnowledgeChunk.objects.create(
        document=document, chunk_id='c1', chapter='第一章', section='长文', page_number=1,
        content='命中片段。' * 20, chunk_type='child', parent_chunk=parent, heading_path='第一章',
    )
    window = build_context(child, budget_tokens=200)
    assert window['truncated'] is True
    assert estimate_tokens(window['context']) <= 260


@pytest.mark.django_db
def test_expand_citations_preserves_legacy_fields():
    document = _document()
    child = KnowledgeChunk.objects.create(
        document=document, chunk_id='c1', chapter='第一章', section='小节', page_number=2,
        content='子块内容。' * 30, chunk_type='child', heading_path='第一章 > 小节',
        char_start=10, char_end=190, content_hash='b' * 64,
    )
    citation = Citation('c1', 'demo.pdf', document.document_hash, '第一章', '小节', 2,
                        child.content, 'original', '1', 0.8, '/knowledge/source/c1/')
    expanded = expand_citations([citation], budget_tokens=500)
    assert expanded[0].chunk_id == 'c1'
    assert expanded[0].document_name == 'demo.pdf'
    assert expanded[0].score == 0.8
    assert expanded[0].context
    assert expanded[0].evidence_id == 'chunk:c1'
    assert expanded[0].matched_content == child.content
