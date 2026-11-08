import hashlib
from pathlib import Path

import pytest
from django.contrib.auth import get_user_model

from apps.knowledge.models import KnowledgeChunk, KnowledgeDocument
from apps.knowledge.services.hierarchical_chunker import estimate_tokens
from apps.knowledge.services.rerank_service import RerankCandidate, rerank
from apps.knowledge.services.rrf_service import reciprocal_rank_fusion
from apps.knowledge.services.query_rewriter import rewrite_query
from apps.knowledge.services.sparse_retrieval import BM25Index, sparse_search


def test_rrf_deduplicates_and_rewards_multiple_routes():
    entries = reciprocal_rank_fusion({'dense::q1': ['a', 'b'], 'sparse::q1': ['b', 'c']}, k=60)
    assert [entry.chunk_id for entry in entries] == ['b', 'a', 'c']
    assert entries[0].score > entries[1].score
    assert ('dense::q1', 2) in entries[0].ranks
    assert ('sparse::q1', 1) in entries[0].ranks


def test_rrf_rejects_invalid_input():
    from core.exceptions import ValidationError
    with pytest.raises(ValidationError):
        reciprocal_rank_fusion({'bad': 123})


def test_bm25_prefers_lexical_match():
    index = BM25Index([('a', '循环队列判满条件是队尾加一等于队头'), ('b', '二叉树的先序中序后序遍历')])
    hits = index.search('循环队列判满', top_k=5)
    assert hits[0].chunk_id == 'a'
    assert hits[0].score == 1.0
    assert sparse_search('二叉树', documents=[('a', '循环队列'), ('b', '二叉树遍历')])[0].chunk_id == 'b'


def test_sparse_returns_empty_for_unrelated_query():
    assert sparse_search('量子引力黑洞', documents=[('a', '循环队列判满')]) == []


def test_heuristic_rewrite_keeps_original_and_never_needs_network():
    result = rewrite_query('循环队列判满条件是什么？', user=None)
    assert result.variants[0] == '循环队列判满条件是什么？'
    assert len(result.variants) >= 2
    assert result.used_fallback is True
    assert result.llm_used is False
    assert all('来源' not in variant for variant in result.variants)


def test_rewrite_code_and_conflict_intents_add_recall_terms():
    result = rewrite_query('Python 版本里这段 def solve() 和另一个实现冲突吗？', user=None)
    joined = ' '.join(result.variants)
    assert '代码' in joined or '实现' in joined
    assert '不同说法' in joined or '对比' in joined


def test_deterministic_rerank_prefers_relevant_authoritative_evidence():
    candidates = [
        RerankCandidate('irrelevant', '二叉树的遍历方式', heading_path='树', authority_level=4, parser_confidence=0.5, freshness=0.5, rrf_score=0.02, raw_score=0.3),
        RerankCandidate('relevant', '循环队列判满条件是队尾加一等于队头', heading_path='队列 > 循环队列', authority_level=1, parser_confidence=1.0, freshness=0.9, rrf_score=0.03, raw_score=0.8),
    ]
    ordered, backend, fallback = rerank('循环队列判满条件', candidates)
    assert backend == 'deterministic'
    assert fallback == ''
    assert ordered[0].chunk_id == 'relevant'
    assert ordered[0].rerank_score > ordered[1].rerank_score


@pytest.fixture
def advanced_document(settings, tmp_path):
    settings.EMBEDDING_PROVIDER = 'tfidf'
    settings.EMBEDDING_MODEL = 'tfidf'
    settings.EMBEDDING_REVISION = 'v1'
    settings.CHROMA_PATH = tmp_path / 'chroma'
    settings.BASE_DIR = tmp_path
    settings.EVIDENCE_RAG_MIN_RERANK_SCORE = 0.0
    document = KnowledgeDocument.objects.create(
        name='数据结构讲义.md', document_hash=hashlib.sha256(b'advanced-doc').hexdigest(),
        path='knowledge/lecture.md', page_count=1,
        embedding_model='tfidf:char-1-3:2048:v1', embedding_revision='v1',
        embedding_dimension=0, index_version='', collection_name='',
        source_type='markdown', authority_level=1, parser_name='markdown',
        ingestion_status='parsed', latest_index_version='',
    )
    from apps.knowledge.services.document_loader import LoadedDocument, SourcePage
    from apps.knowledge.services.multimodal_loader import ParsedDocument
    from apps.knowledge.services.advanced_index_service import index_advanced_chunks, parse_and_store_advanced
    text = '''# 第三章 栈与队列

## 3.1 循环队列

循环队列使用固定大小数组。队头指针 front 指向队首元素，队尾指针 rear 指向队尾元素的下一个位置。

循环队列判空条件是 front == rear。

循环队列判满条件是 (rear + 1) % maxsize == front。

为了区分队空和队满，通常牺牲一个存储单元。队列中最多存放 maxsize - 1 个元素。

## 3.2 栈

栈是后进先出的线性表。顺序栈使用数组和栈顶指针。链栈使用链表。入栈和出栈都在栈顶进行。
''' + ('队列操作的时间复杂度为 O(1)。' * 40)
    loaded = LoadedDocument(Path('knowledge/lecture.md'), '数据结构讲义.md', document.document_hash, (SourcePage(1, text),))
    parsed = ParsedDocument(loaded, 'markdown', 'markdown', '', (), (), {'test': True})
    counts = parse_and_store_advanced(document, parsed)
    index = index_advanced_chunks(document, rebuild=True)
    document.refresh_from_db()
    return document, counts, index


@pytest.mark.django_db
def test_advanced_retrieval_returns_trace_small2big_and_parent_links(advanced_document):
    from apps.knowledge.services.hybrid_retrieval import advanced_retrieve
    document, counts, index = advanced_document
    user = get_user_model().objects.create_user('advanced-reader')
    result = advanced_retrieve('循环队列判满条件', user=user)
    assert result.mode == 'advanced'
    assert result.trace_id
    assert result.query_variants
    assert result.citations
    assert any('判满' in citation.content for citation in result.citations)
    assert any(citation.parent_chunk_id for citation in result.citations)
    assert any(citation.context for citation in result.citations)
    assert result.rerank_backend == 'deterministic'
    assert result.query_route['low_confidence'] is False
    assert 'scores_close' in result.query_route
    assert result.retrieval_trace
    assert 'dense' in {row['retriever_name'] for row in result.retrieval_trace}
    assert 'sparse' in {row['retriever_name'] for row in result.retrieval_trace}
    assert document.latest_index_version == index['index_version']
    assert KnowledgeChunk.objects.filter(document=document, chunk_type='parent').count() == counts['parents']


@pytest.mark.django_db
def test_advanced_retrieval_refuses_unrelated_query(advanced_document):
    from apps.knowledge.services.hybrid_retrieval import advanced_retrieve
    user = get_user_model().objects.create_user('refusal-reader')
    result = advanced_retrieve('量子引力黑洞霍金辐射', user=user)
    assert result.mode == 'advanced'
    assert result.citations == []
    assert result.evidence_sufficient is False
    assert result.query_route['evidence_gate']['kept_candidates'] == 0


@pytest.mark.django_db
def test_advanced_retrieval_without_index_falls_back_legacy(settings):
    from apps.knowledge.services.hybrid_retrieval import advanced_retrieve
    user = get_user_model().objects.create_user('fallback-reader')
    result = advanced_retrieve('循环队列判满条件', user=user)
    assert result.mode == 'legacy'
    assert result.fallback['used'] is True
    assert result.fallback['reason'] == 'ADVANCED_INDEX_MISSING'
    assert result.trace_id


@pytest.mark.django_db
def test_legacy_wrapper_preserves_citation_contract(settings, monkeypatch):
    from apps.knowledge.services import retrieval_service
    from apps.knowledge.services.retrieval_service import Citation
    citation = Citation('legacy-1', 'legacy.pdf', 'hash', '第一章', '小节', 2, '旧版证据', 'original', '1', 0.9, '/knowledge/source/legacy-1/')
    monkeypatch.setattr(retrieval_service, 'retrieve_knowledge', lambda query, top_k=None: [citation])
    result = retrieval_service.retrieve_knowledge_with_trace('循环队列', mode='legacy')
    assert result.mode == 'legacy'
    assert result.citations == [citation]
    assert citation.chunk_id == 'legacy-1'
    assert citation.document_name == 'legacy.pdf'
    assert citation.score == 0.9
