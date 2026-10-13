"""Actual LangChain graph routing with explicit LLM/HTTP test doubles."""
from unittest.mock import patch
import json
import pytest
from cryptography.fernet import Fernet
from django.contrib.auth import get_user_model
from apps.accounts.services.credential_service import save_config
from apps.agents.models import ToolInvocation
from apps.agents.services.agent_service import run_agent
from apps.tutor.services.chat_service import answer
from core.llm.provider import LLMResult, TokenUsage

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def learner(settings):
    settings.APP_ENCRYPTION_KEY = Fernet.generate_key().decode()
    user = get_user_model().objects.create_user('wiki-routing-test')
    save_config(user, 'sk-test-key-12345678', default_tier='deep')
    return user


WIKI = {'success': True, 'found': True, 'title': '红黑树', 'summary': '一种自平衡二叉搜索树。',
        'extract': '一种自平衡二叉搜索树。', 'query': '红黑树', 'source_type': 'wikipedia',
        'source_url': 'https://zh.wikipedia.org/wiki/红黑树', 'url': 'https://zh.wikipedia.org/wiki/红黑树',
        'page_id': 55999, 'language': 'zh', 'from_cache': False, 'cache_status': 'FRESH',
        'retrieved_at': '2026-10-13T00:00:00+00:00'}


class AnswerClient:
    def __init__(self):
        self.messages = []

    def complete(self, messages, **kwargs):
        self.messages.append((messages, kwargs))
        return LLMResult('请查看实际来源 [维基百科：红黑树]。', TokenUsage(), 'deepseek-flash')


def test_explicit_wikipedia_invokes_registered_tool_inside_graph_and_keeps_thinking_tier(learner):
    client = AnswerClient()
    with patch('apps.agents.services.tool_registry.WikipediaProvider.search', return_value=WIKI) as search:
        result = run_agent(learner, '使用维基百科查询红黑树。我的学号123456不要发送给百科。', client=client)
    assert search.call_args.kwargs['query'] == '红黑树'
    assert result.external_sources == [WIKI]
    assert ToolInvocation.objects.get().tool_name == 'search_wikipedia'
    assert client.messages[0][1]['tier'] == 'deep'
    assert 'tool_choice' not in client.messages[0][1]
    assert '"page_id": 55999' in client.messages[0][0][0]['content']
    assert '123456' not in str(search.call_args)


def test_realtime_request_does_not_silently_use_fresh_cache(learner):
    with patch('apps.agents.services.tool_registry.WikipediaProvider.search', return_value=WIKI) as search:
        run_agent(learner, '实时查询维基百科红黑树', client=AnswerClient())
    assert search.call_args.kwargs['force_refresh'] is True


def test_personal_statistics_without_external_request_does_not_call_wikipedia(learner):
    with patch('apps.agents.services.tool_registry.WikipediaProvider.search') as search:
        run_agent(learner, '我本周做了多少道链表题？', client=AnswerClient())
    assert not search.called


def test_multi_tool_wikipedia_and_real_student_query_are_preserved(learner):
    class StudentClient(AnswerClient):
        def complete(self, messages, **kwargs):
            self.messages.append((messages, kwargs))
            if len(self.messages) == 1:
                return LLMResult('', TokenUsage(), 'deepseek-flash', ({'id': 'student-data', 'type': 'function', 'function': {'name': 'query_student_learning', 'arguments': json.dumps({'days': 7})}},), 'transient reasoning', 'tool_calls')
            assert any(message['role'] == 'tool' for message in messages)
            return LLMResult('百科已获取，当前没有有效树结构练习记录。', TokenUsage(), 'deepseek-flash')
    with patch('apps.agents.services.tool_registry.WikipediaProvider.search', return_value=WIKI):
        result = run_agent(learner, '通过维基百科解释红黑树，再查我的做题记录。', client=StudentClient())
    assert {item['tool_name'] for item in result.tool_invocations} == {'search_wikipedia', 'query_student_learning'}


def test_chat_persists_external_sources_without_changing_course_citation_validation(learner):
    with patch('apps.tutor.services.chat_service.retrieve_knowledge', return_value=[]), \
         patch('apps.agents.services.tool_registry.WikipediaProvider.search', return_value=WIKI), \
         patch('apps.agents.services.agent_service.DeepSeekClient', return_value=AnswerClient()):
        result = answer(learner, '什么是红黑树？')
    assert result.external_sources == [WIKI] and result.citations == [WIKI]
    from apps.tutor.models import ChatMessage
    assert ChatMessage.objects.get(pk=result.message_id).citations == [WIKI]


def test_sufficient_course_evidence_does_not_request_wikipedia(learner):
    from types import SimpleNamespace
    evidence = [SimpleNamespace(document_name='课程.pdf', chapter='队列', page_number=9, chunk_id='queue', content='循环队列判满条件。')]
    with patch('apps.tutor.services.chat_service.retrieve_knowledge', return_value=evidence), \
         patch('apps.tutor.services.chat_service.citations_json', return_value=[{'source_type': 'original'}]), \
         patch('apps.agents.services.tool_registry.WikipediaProvider.search') as search, \
         patch('apps.agents.services.agent_service.DeepSeekClient', return_value=AnswerClient()):
        answer(learner, '循环队列如何判断队满？')
    assert not search.called


def test_uncovered_public_concept_outside_reviewed_aliases_is_still_retrieved(learner):
    with patch('apps.tutor.services.chat_service.retrieve_knowledge', return_value=[]), \
         patch('apps.agents.services.tool_registry.WikipediaProvider.search', return_value=WIKI) as search, \
         patch('apps.agents.services.agent_service.DeepSeekClient', return_value=AnswerClient()):
        answer(learner, '什么是 Treap？')
    assert search.call_args.kwargs['query'] == 'Treap'


def test_unsafe_uncovered_question_is_not_sent_as_an_external_query(learner):
    with patch('apps.tutor.services.chat_service.retrieve_knowledge', return_value=[]), \
         patch('apps.agents.services.tool_registry.WikipediaProvider.search') as search, \
         patch('apps.agents.services.agent_service.DeepSeekClient', return_value=AnswerClient()):
        answer(learner, '请解释我的学生成绩记录 secret123')
    assert not search.called
