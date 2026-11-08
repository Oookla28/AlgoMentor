from apps.knowledge.services.citation_verifier import verify_answer
from apps.knowledge.services.retrieval_service import Citation, verified_citation_ids
from core.exceptions import KnowledgeRetrievalError

import pytest


def _citation(chunk_id, content):
    return Citation(chunk_id, 'demo.pdf', 'hash', '第一章', '小节', 1, content, 'original', '1', 0.9, f'/knowledge/source/{chunk_id}/')


def test_valid_citations_pass():
    citations = [_citation('c1', '循环队列判满条件是 (rear+1)%maxsize == front。')]
    check = verify_answer('循环队列判满条件是 (rear+1)%maxsize == front。[来源1]', citations)
    assert check['out_of_range'] == []
    assert check['passed'] is True
    assert check['claim_coverage'] == 1.0


def test_out_of_range_citation_is_rejected_by_legacy_and_new_checker():
    citations = [_citation('c1', '循环队列判满条件')]
    with pytest.raises(KnowledgeRetrievalError):
        verified_citation_ids('见[来源9]', citations)
    check = verify_answer('循环队列判满条件。[来源9]', citations)
    assert check['out_of_range'] == [9]
    assert check['passed'] is False


def test_missing_citation_is_reported():
    citations = [_citation('c1', '栈是后进先出的线性表。')]
    check = verify_answer('栈是一种后进先出的数据结构。', citations)
    assert check['missing_citations']
    assert check['claim_coverage'] == 0.0


def test_unsupported_claim_is_reported():
    citations = [_citation('c1', '循环队列判满条件是队尾加一等于队头。')]
    check = verify_answer('红黑树的插入操作需要旋转和重新着色。[来源1]', citations)
    assert check['unsupported_claims']
    assert check['passed'] is False


def test_contradictory_claim_is_reported():
    citations = [_citation('c1', '循环队列使用一个空闲单元区分队空和队满，因此最多存放 maxsize-1 个元素。')]
    check = verify_answer('循环队列不使用空闲单元，可以存放 maxsize 个元素。[来源1]', citations)
    assert check['contradictions'] or check['unsupported_claims']
    assert check['passed'] is False
