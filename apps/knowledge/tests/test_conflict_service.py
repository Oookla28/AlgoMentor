from types import SimpleNamespace
import hashlib

import pytest

from apps.knowledge.services.conflict_service import classify_pair, detect_conflicts, detect_and_store_conflicts, serialize_conflict


def _claim(claim_id, text, authority=3, chunk_id=None, score=0.6, predicate='是'):
    chunk_id = chunk_id or f'chunk-{claim_id}'
    return SimpleNamespace(
        claim_id=claim_id, normalized_text=text, authority_level=authority, detector_score=score,
        predicate=predicate,
        source_chunk_id=chunk_id, source_chunk=SimpleNamespace(chunk_id=chunk_id),
        valid_from=None, valid_to=None, created_at=None,
    )


def test_classify_negation_number_version_and_temporal():
    assert classify_pair('循环队列判满条件是队尾加一等于队头', '循环队列判满条件不是队尾加一等于队头', threshold=0.5).conflict_type == 'NEGATION'
    assert classify_pair('循环队列最多存放 maxsize 个元素', '循环队列最多存放 maxsize-1 个元素', threshold=0.5).conflict_type == 'NUMERIC'
    assert classify_pair('该算法在 v1.0 版本使用插入排序', '该算法在 v2.0 版本使用插入排序', threshold=0.4).conflict_type == 'VERSION'
    assert classify_pair('2023 年的课程要求使用递归实现', '2025 年的课程要求使用递归实现', threshold=0.4).conflict_type == 'TEMPORAL'


def test_low_similarity_is_not_a_conflict():
    assert classify_pair('循环队列判满条件', '二叉树的中序遍历', threshold=0.5) is None


def test_detect_conflicts_marks_unresolved_when_scores_are_close():
    claims = [
        _claim('a', '循环队列判满条件是队尾加一等于队头', authority=2),
        _claim('b', '循环队列判满条件不是队尾加一等于队头', authority=2),
    ]
    conflicts = detect_conflicts(claims, similarity_threshold=0.4, score_gap=0.2)
    assert len(conflicts) == 1
    assert conflicts[0].verdict == 'UNRESOLVED'
    assert conflicts[0].conflict_type == 'NEGATION'
    assert '暂不能确定' in conflicts[0].explanation


def test_optional_nli_backend_is_consulted_only_after_similarity_gate():
    from apps.knowledge.services.conflict_service import ConflictSignal
    claims = [_claim('a', '循环队列判满条件'), _claim('b', '循环队列判空条件')]
    calls = []

    def backend(claim_a, claim_b):
        calls.append((claim_a.claim_id, claim_b.claim_id))
        return ConflictSignal('STANCE', 0.9)

    conflicts = detect_conflicts(claims, similarity_threshold=0.9, score_gap=0.01, backend=backend)
    assert calls
    assert conflicts and conflicts[0].conflict_type == 'STANCE'


def test_detect_conflicts_can_prefer_more_authoritative_claim():
    claims = [
        _claim('a', '循环队列判满条件是队尾加一等于队头', authority=1),
        _claim('b', '循环队列判满条件不是队尾加一等于队头', authority=5),
    ]
    conflicts = detect_conflicts(claims, similarity_threshold=0.4, score_gap=0.05)
    assert conflicts[0].verdict == 'A_WINS'


@pytest.mark.django_db
def test_store_and_serialize_conflict():
    from apps.knowledge.models import EvidenceClaim, KnowledgeConflict, KnowledgeDocument, KnowledgeQueryTrace, KnowledgeChunk
    document = KnowledgeDocument.objects.create(
        name='demo.pdf', document_hash=hashlib.sha256(b'conflict-demo').hexdigest(), path='demo.pdf',
        page_count=1, embedding_model='tfidf:char-1-3:2048:v1', embedding_revision='v1',
        embedding_dimension=8, index_version='idx', collection_name='course-idx',
    )
    first = KnowledgeChunk.objects.create(document=document, chunk_id='c1', chapter='第一章', section='队列', page_number=1, content='循环队列判满条件是队尾加一等于队头。')
    second = KnowledgeChunk.objects.create(document=document, chunk_id='c2', chapter='第二章', section='队列', page_number=2, content='循环队列判满条件不是队尾加一等于队头。')
    claim_a = EvidenceClaim.objects.create(claim_id='a', source_chunk=first, normalized_text=first.content, subject='循环队列', predicate='是', object='队尾加一等于队头')
    claim_b = EvidenceClaim.objects.create(claim_id='b', source_chunk=second, normalized_text=second.content, subject='循环队列', predicate='不是', object='队尾加一等于队头')
    trace = KnowledgeQueryTrace.objects.create(trace_id='trace-conflict', original_query='判满条件', retrieval_mode='advanced')
    stored = detect_and_store_conflicts(trace, [claim_a, claim_b])
    assert stored and isinstance(stored[0], KnowledgeConflict)
    payload = serialize_conflict(stored[0])
    assert payload['conflict_type'] in ('NEGATION', 'STANCE')
    assert payload['claim_a']['chunk_id'] == 'c1'
    assert payload['verdict_label']
