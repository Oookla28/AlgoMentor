import pytest

from apps.platform.agent import AgentBudget, run_evidence_agent
from apps.platform.contracts import ToolResult
from apps.platform.models import AgentRun


def _item(chunk_id='c1', content='循环队列判满条件是 (rear+1)%MaxSize == front。', page=9, authority=1):
    return {
        'chunk_id': chunk_id, 'document_id': 1, 'document_name': '数据结构与算法知识库文档.pdf',
        'document_hash': 'hash', 'chapter': '第三章', 'section': '队列', 'page': page,
        'chunk_type': 'child', 'heading_path': '第三章 > 队列', 'content': content,
        'char_start': 0, 'char_end': len(content), 'content_hash': 'a' * 64,
        'source_version': '1', 'authority_level': authority, 'valid_from': '', 'valid_to': '',
        'source_type': 'original', 'parent_chunk_id': 'p1', 'media_asset_id': '',
        'start_time': None, 'end_time': None, 'modality': 'text',
        'retrieval_score': 0.9, 'rank': 1, 'retriever': 'dense',
    }


@pytest.fixture
def user(django_user_model):
    return django_user_model.objects.create_user('agent-user', password='test-password')


@pytest.fixture(autouse=True)
def patch_capabilities(monkeypatch):
    monkeypatch.setattr(
        'apps.platform.agent.state_machine.capability_map',
        lambda: {'advanced_index': {'state': 'available'}, 'embedding': {'state': 'fallback'}},
    )


@pytest.mark.django_db
def test_agent_completes_with_grounded_answer(user, monkeypatch):
    def fake_tool(tool_id, _user, **kwargs):
        return ToolResult(True, tool_id, output={'results': [_item()]}, evidence_ids=('c1',))

    monkeypatch.setattr('apps.platform.agent.state_machine.execute_tool', fake_tool)
    outcome = run_evidence_agent(user, '循环队列判满条件', budget=AgentBudget())
    assert outcome.status == 'COMPLETED'
    assert '[来源1]' in outcome.answer
    run = AgentRun.objects.get(run_id=outcome.run_id)
    assert run.status == 'COMPLETED'
    assert {'START', 'ROUTE', 'PLAN', 'CALL_TOOL', 'RETRIEVE', 'EVIDENCE_GATE', 'CONFLICT_CHECK', 'VERIFY', 'ANSWER', 'END'} <= set(run.steps.values_list('step_type', flat=True))
    assert all(len(step.output_summary) <= 500 for step in run.steps.all())
    assert run.evidence.count() >= 1
    assert run.metrics['gate']['decision'] == 'PASS'


@pytest.mark.django_db
def test_agent_abstains_without_evidence(user, monkeypatch):
    def empty_tool(tool_id, _user, **kwargs):
        return ToolResult(True, tool_id, output={'results': []}, evidence_ids=())

    monkeypatch.setattr('apps.platform.agent.state_machine.execute_tool', empty_tool)
    outcome = run_evidence_agent(user, '量子引力黑洞霍金辐射', budget=AgentBudget())
    assert outcome.status == 'ABSTAINED'
    assert '没有提供充分证据' in outcome.answer
    run = AgentRun.objects.get(run_id=outcome.run_id)
    assert run.steps.filter(step_type='ABSTAIN').exists()


@pytest.mark.django_db
def test_agent_budget_forces_abstention(user, monkeypatch):
    def fake_tool(tool_id, _user, **kwargs):
        return ToolResult(True, tool_id, output={'results': [_item()]}, evidence_ids=('c1',))

    monkeypatch.setattr('apps.platform.agent.state_machine.execute_tool', fake_tool)
    outcome = run_evidence_agent(user, '循环队列判满条件', budget=AgentBudget(max_steps=4))
    assert outcome.status == 'ABSTAINED'
    run = AgentRun.objects.get(run_id=outcome.run_id)
    assert 'BUDGET_EXCEEDED' in run.error_code


@pytest.mark.django_db
def test_agent_records_conflict_set(user, monkeypatch):
    first = _item('c1', '循环队列判满条件是队尾加一等于队头。', page=9)
    second = _item('c2', '循环队列判满条件不是队尾加一等于队头。', page=10, authority=3)

    def fake_tool(tool_id, _user, **kwargs):
        return ToolResult(True, tool_id, output={'results': [first, second]}, evidence_ids=('c1', 'c2'))

    monkeypatch.setattr('apps.platform.agent.state_machine.execute_tool', fake_tool)
    outcome = run_evidence_agent(user, '循环队列判满条件', budget=AgentBudget())
    run = AgentRun.objects.get(run_id=outcome.run_id)
    assert run.conflict_sets.count() == 1
    assert run.metrics['gate']['conflict_count'] >= 1
