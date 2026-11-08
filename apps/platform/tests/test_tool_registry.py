from types import SimpleNamespace
import time

import pytest

from apps.platform.contracts import ToolSpec
from apps.platform.tools import execute_spec, execute_tool


def _user(staff=False):
    return SimpleNamespace(is_authenticated=True, is_active=True, pk=7, is_staff=staff)


def test_permission_rejection_for_write_tool():
    spec = ToolSpec(tool_id='write_probe', version='1', name='write', description='probe', permission='write')
    result = execute_spec(spec, lambda user: {'results': []}, _user(staff=False))
    assert result.ok is False
    assert result.failure_code == 'TOOL_PERMISSION_DENIED'


def test_timeout_is_enforced():
    def slow(_user):
        time.sleep(0.25)
        return {'results': []}

    spec = ToolSpec(tool_id='slow_probe', version='1', name='slow', description='probe', timeout_seconds=0.05)
    result = execute_spec(spec, slow, _user())
    assert result.ok is False
    assert result.failure_code == 'TOOL_TIMEOUT'


def test_invalid_tool_call_is_rejected():
    result = execute_tool('missing_tool', _user())
    assert result.ok is False
    assert result.failure_code == 'TOOL_NOT_FOUND'


@pytest.mark.django_db(transaction=True)
def test_keyword_and_parent_tools_read_real_chunks():
    import hashlib
    from apps.knowledge.models import KnowledgeChunk, KnowledgeDocument
    document = KnowledgeDocument.objects.create(
        name='tool-demo.pdf', document_hash=hashlib.sha256(b'tool-demo').hexdigest(), path='demo.pdf',
        page_count=1, embedding_model='tfidf:char-1-3:2048:v1', embedding_revision='v1',
        embedding_dimension=2048, index_version='idx', collection_name='course-idx',
        source_type='pdf', authority_level=1, ingestion_status='ready',
    )
    parent = KnowledgeChunk.objects.create(
        document=document, chunk_id='p1', chapter='第三章', section='队列', page_number=1,
        content='循环队列使用数组存储，牺牲一个单元区分队空队满。' * 5,
        chunk_type='parent', heading_path='第三章 > 队列',
    )
    child = KnowledgeChunk.objects.create(
        document=document, chunk_id='c1', chapter='第三章', section='队列', page_number=1,
        content='循环队列判满条件是 (rear+1)%MaxSize == front。',
        chunk_type='child', parent_chunk=parent, heading_path='第三章 > 队列',
    )
    user = _user()
    result = execute_tool('keyword_search', user, query='循环队列判满', top_k=5)
    assert result.ok is True
    assert any(item['chunk_id'] in {'c1', 'p1'} for item in result.output['results'])
    parent_result = execute_tool('read_parent', user, chunk_id=child.chunk_id)
    assert parent_result.ok is True
    assert parent_result.output['result']['chunk_id'] == parent.chunk_id
    sibling_result = execute_tool('read_siblings', user, chunk_id=child.chunk_id)
    assert sibling_result.ok is True
    page_result = execute_tool('read_source_page', user, chunk_id=child.chunk_id)
    assert page_result.ok is True
    assert page_result.output['results']
