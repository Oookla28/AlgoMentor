from pathlib import Path

import pytest
from django.contrib.auth import get_user_model
from django.test import override_settings

from apps.knowledge.models import KnowledgeChunk, KnowledgeDocument
from apps.platform.models import AgentRun
from apps.workspace.models import TaskArtifact, Workspace, WorkspaceDocument
from apps.workspace.services import executor
from apps.workspace.services.tasks import claim_next, create_task, recover_stale_runs, retry_task


def make_document(name, content, hash_seed):
    document = KnowledgeDocument.objects.create(
        name=name, document_hash=f'hash-{hash_seed}', path=f'{name}', page_count=1,
        embedding_model='tfidf', embedding_revision='', embedding_dimension=2048,
        index_version='', collection_name='',
    )
    chunk = KnowledgeChunk.objects.create(
        document=document, chunk_id=f'chunk-{hash_seed}', chapter='第一章', section=name,
        page_number=1, content=content, chunk_type='child', heading_path=name,
        char_start=0, char_end=len(content),
    )
    return document, chunk


def make_workspace(user, domain='generic', name='空间'):
    return Workspace.objects.create(name=name, owner=user, domain_pack_id=domain)


def link(workspace, user, document, status='ready'):
    return WorkspaceDocument.objects.create(
        workspace=workspace, document=document, added_by=user, original_name=document.name, status=status,
    )


@pytest.mark.django_db
def test_workspace_chunk_ids_use_the_salted_document_hash():
    from pathlib import Path
    from apps.knowledge.services.advanced_index_service import parse_and_store_advanced
    from apps.knowledge.services.document_loader import LoadedDocument, SourcePage
    from apps.knowledge.services.multimodal_loader import ParsedDocument

    text = '# 笔记\n\n同一份资料在不同空间不能共享片段 ID。' * 20
    loaded = LoadedDocument(Path('same.md'), 'same.md', 'original-hash', (SourcePage(1, text),))
    parsed = ParsedDocument(loaded, 'markdown', 'plain-text', '')
    document = KnowledgeDocument.objects.create(
        name='same.md', document_hash='salted-hash-1234567890', path='same.md', page_count=1,
        embedding_model='tfidf', embedding_revision='', embedding_dimension=0,
        index_version='', collection_name='',
    )
    parse_and_store_advanced(document, parsed)
    chunks = list(document.chunks.all())
    assert chunks
    assert all(chunk.chunk_id.startswith('adv-salted-hash') for chunk in chunks)
    assert not any(chunk.chunk_id.startswith('adv-original-has') for chunk in chunks)


@pytest.mark.django_db(transaction=True)
def test_grounded_qa_task_is_scoped_and_persisted():
    User = get_user_model()
    user = User.objects.create_user('qa-user', password='x')
    workspace = make_workspace(user)
    other = make_workspace(user, name='另一个空间')
    document, _chunk = make_document(
        'queue.md',
        '循环队列判满条件是 (rear + 1) % max_size == front。队空条件是 front == rear。'
        '循环队列的入队和出队时间复杂度均为 O(1)。',
        'queue',
    )
    decoy, _decoy_chunk = make_document(
        'physics.md', '量子引力与黑洞霍金辐射是物理学问题，不是循环队列的判满条件。', 'physics',
    )
    link(workspace, user, document)
    link(other, user, decoy)
    run = create_task(user, workspace, 'grounded_qa', '循环队列判满条件是什么？')
    assert run.status == 'QUEUED'
    claimed = claim_next('test-worker')
    assert claimed.run_id == run.run_id
    result = executor.execute_run(run.run_id)
    assert result.status == 'SUCCEEDED'
    assert result.evidence_count >= 1
    evidence_text = ' '.join(item.content for item in result.evidence.all())
    assert '循环队列' in evidence_text
    assert '量子引力' not in evidence_text
    assert result.artifacts.count() == 0
    assert result.steps.filter(step_type='END').exists()


@pytest.mark.django_db(transaction=True)
def test_unknown_question_abstains_without_cross_workspace_leak():
    User = get_user_model()
    user = User.objects.create_user('abstain-user', password='x')
    workspace = make_workspace(user)
    document, _chunk = make_document(
        'queue.md', '循环队列判满条件是 (rear + 1) % max_size == front。', 'queue2',
    )
    decoy, _decoy = make_document('secret.md', '量子引力与黑洞霍金辐射。', 'secret')
    link(workspace, user, document)
    other = make_workspace(user, name='另一个私有空间')
    link(other, user, decoy)
    run = create_task(user, workspace, 'grounded_qa', '黑洞霍金辐射的温度是多少？')
    claim_next('test-worker')
    result = executor.execute_run(run.run_id)
    assert result.status == 'ABSTAINED'
    assert result.stage == '已拒答'
    assert result.evidence_count == 0


@pytest.mark.django_db
def test_cancel_and_retry_are_real_state_transitions():
    User = get_user_model()
    user = User.objects.create_user('cancel-user', password='x')
    workspace = make_workspace(user)
    document, _chunk = make_document('queue.md', '循环队列判满条件。', 'cancel')
    link(workspace, user, document)
    run = create_task(user, workspace, 'grounded_qa', '循环队列判满条件？')
    run.cancel_requested = True
    run.status = 'RUNNING'
    run.save(update_fields=['cancel_requested', 'status'])
    result = executor.execute_run(run.run_id)
    assert result.status == 'CANCELLED'
    assert result.error_code == 'CANCELLED_BY_USER'

    retry_source = AgentRun.objects.create(
        run_id='retry-source', user=user, workspace=workspace, domain='generic',
        task_type='grounded_qa', query='循环队列判满条件？', status='FAILED',
    )
    new_run = retry_task(user, retry_source)
    assert new_run.run_id != retry_source.run_id
    assert new_run.status == 'QUEUED'
    assert new_run.input_payload['retry_of'] == 'retry-source'


@pytest.mark.django_db
def test_stale_lease_is_requeued_then_failed_after_attempts():
    User = get_user_model()
    user = User.objects.create_user('stale-user', password='x')
    workspace = make_workspace(user)
    document, _chunk = make_document('queue.md', '循环队列判满条件。', 'stale')
    link(workspace, user, document)
    run = create_task(user, workspace, 'grounded_qa', '循环队列判满条件？')
    from django.utils import timezone
    from datetime import timedelta
    run.status = 'RUNNING'
    run.attempts = 1
    run.lease_expires_at = timezone.now() - timedelta(seconds=5)
    run.save(update_fields=['status', 'attempts', 'lease_expires_at'])
    report = recover_stale_runs(max_attempts=2)
    run.refresh_from_db()
    assert report['requeued'] == 1
    assert run.status == 'QUEUED'

    run.status = 'RUNNING'
    run.attempts = 2
    run.lease_expires_at = timezone.now() - timedelta(seconds=5)
    run.save(update_fields=['status', 'attempts', 'lease_expires_at'])
    report = recover_stale_runs(max_attempts=2)
    run.refresh_from_db()
    assert report['failed'] == 1
    assert run.status == 'FAILED'
    assert run.error_code == 'WORKER_LOST'


@pytest.mark.django_db
def test_paper_comparison_builds_markdown_and_html(monkeypatch):
    User = get_user_model()
    user = User.objects.create_user('paper-user', password='x')
    workspace = make_workspace(user, domain='research_literature', name='论文')
    doc_a, chunk_a = make_document(
        'paper-a.md',
        '方法：本文提出块稀疏注意力。实验使用 LongBench 数据集与全注意力基线。'
        '结论：延迟降低 38%。局限：未覆盖多模态。',
        'paper-a',
    )
    doc_b, chunk_b = make_document(
        'paper-b.md',
        '方法：本文提出多查询证据覆盖。实验使用三个中文问答数据集与 BM25 基线。'
        '结论：Recall@5 提升到 0.74。局限：没有标注者一致性。',
        'paper-b',
    )
    link(workspace, user, doc_a)
    link(workspace, user, doc_b)
    items = []
    for document, chunk in ((doc_a, chunk_a), (doc_b, chunk_b)):
        items.append({
            'chunk_id': chunk.chunk_id, 'document_id': document.pk, 'document_name': document.name,
            'document_hash': document.document_hash, 'page': 1, 'content': chunk.content,
            'heading_path': chunk.heading_path, 'char_start': 0, 'char_end': len(chunk.content),
            'content_hash': chunk.content_hash, 'source_version': '1', 'authority_level': 3,
            'retrieval_score': 0.9, 'retriever': 'bm25', 'source_type': 'text',
            'parent_chunk_id': '', 'modality': 'text',
        })

    def fake_search(recorder, user, run, query, document_ids, top_k=12):
        return [item for item in items if item['document_id'] in document_ids][:top_k]

    monkeypatch.setattr(executor, '_search', fake_search)
    run = create_task(user, workspace, 'paper_comparison', '比较方法、实验和局限')
    claim_next('test-worker')
    result = executor.execute_run(run.run_id)
    assert result.status in ('SUCCEEDED', 'PARTIAL')
    artifact = TaskArtifact.objects.get(run=result, kind='comparison', format='markdown')
    assert '| 文献 | 方法 | 实验条件 | 主要结论 | 局限 |' in artifact.content
    assert '不是系统综述' in artifact.content
    assert TaskArtifact.objects.filter(run=result, kind='comparison', format='html').exists()
    assert result.skill_activations.filter(skill_id='evidence-paper-comparison').exists()


@pytest.mark.django_db
def test_code_investigation_marks_execution_unverified(monkeypatch, tmp_path):
    User = get_user_model()
    user = User.objects.create_user('code-user', password='x')
    workspace = make_workspace(user, domain='software_engineering', name='代码')
    code_path = tmp_path / 'inventory.py'
    code_path.write_text(
        'def take(item):\n'
        '    if item == None:\n'
        '        return\n'
        '    try:\n'
        '        item.stock -= 1\n'
        '    except Exception:\n'
        '        pass\n',
        encoding='utf-8',
    )
    document = KnowledgeDocument.objects.create(
        name='inventory.py', document_hash='hash-code', path=str(code_path), page_count=1,
        embedding_model='tfidf', embedding_revision='', embedding_dimension=2048,
        index_version='', collection_name='',
    )
    chunk = KnowledgeChunk.objects.create(
        document=document, chunk_id='chunk-code', chapter='', section='inventory.py',
        page_number=1, content=code_path.read_text(encoding='utf-8'), chunk_type='child',
    )
    link(workspace, user, document)
    item = {
        'chunk_id': chunk.chunk_id, 'document_id': document.pk, 'document_name': document.name,
        'document_hash': document.document_hash, 'page': 1, 'content': chunk.content,
        'heading_path': 'inventory.py', 'char_start': 0, 'char_end': len(chunk.content),
        'content_hash': chunk.content_hash, 'source_version': '1', 'authority_level': 1,
        'retrieval_score': 0.9, 'retriever': 'bm25', 'source_type': 'text',
        'parent_chunk_id': '', 'modality': 'text',
    }

    def fake_search(recorder, user, run, query, document_ids, top_k=12):
        return [item] if document.pk in document_ids else []

    monkeypatch.setattr(executor, '_search', fake_search)
    with override_settings(EVIDENCE_RAG_UPLOAD_DIR=tmp_path):
        run = create_task(user, workspace, 'code_investigation', '检查库存扣减的异常处理')
        claim_next('test-worker')
        result = executor.execute_run(run.run_id)
    assert result.status in ('SUCCEEDED', 'PARTIAL')
    report = TaskArtifact.objects.get(run=result, kind='code_report', format='markdown')
    assert 'UNVERIFIED' in report.content
    assert '建议补丁' in report.content
    patch = TaskArtifact.objects.filter(run=result, kind='suggested_patch').first()
    assert patch is not None
    assert '-    if item == None:' in patch.content
    assert '+    if item is None:' in patch.content
    assert result.metrics.get('execution_status') == 'UNVERIFIED'
