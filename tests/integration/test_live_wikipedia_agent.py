"""Opt-in: real LangChain and real Wikimedia, with an explicitly fake LLM planner."""
import json
import os
from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from django.contrib.auth import get_user_model
from django.utils import timezone
from apps.accounts.services.credential_service import save_config
from apps.agents.services.agent_service import run_agent
from apps.knowledge.models import WikipediaCache
from core.llm.provider import LLMResult, TokenUsage


@pytest.mark.skipif(os.environ.get('ALGOMENTOR_LIVE_WIKIPEDIA') != '1', reason='Explicit Wikimedia live integration only')
@pytest.mark.django_db(transaction=True)
def test_real_wikipedia_inside_langchain_and_multi_tool_student_lookup(settings):
    settings.APP_ENCRYPTION_KEY = Fernet.generate_key().decode()
    user = get_user_model().objects.create_user('wikipedia-live-test-only')
    save_config(user, 'sk-test-key-12345678', default_tier='deep')

    class Planner:
        def __init__(self):
            self.calls = 0

        def complete(self, messages, **kwargs):
            self.calls += 1
            assert '"source_type": "wikipedia"' in messages[0]['content']
            if self.calls == 1:
                return LLMResult('', TokenUsage(), 'deepseek-flash', ({'id': 'learning-live', 'type': 'function', 'function': {'name': 'query_student_learning', 'arguments': '{"days":7}'}},), 'test-only transient reasoning', 'tool_calls')
            assert any(item['role'] == 'tool' for item in messages)
            return LLMResult('百科资料已经取得；此测试用户没有真实树结构练习记录。', TokenUsage(), 'deepseek-flash')

    result = run_agent(user, '实时使用维基百科解释红黑树，再查我此前做过的题目。', client=Planner())
    assert {tool['tool_name'] for tool in result.tool_invocations} == {'search_wikipedia', 'query_student_learning'}
    source = result.external_sources[0]
    assert source['success'] and not source['from_cache'] and source['page_id'] > 0
    assert source['source_url'].startswith('https://zh.wikipedia.org/wiki/')
    assert WikipediaCache.objects.count() == 1
    assert '此前' not in WikipediaCache.objects.get().query
    evidence = {'executed_at': timezone.now().isoformat(), 'status': 'PASSED',
                'framework': 'real LangChain create_agent', 'wikipedia_transport': 'real official Action API',
                'llm_planner': 'explicit test double; no DeepSeek inference or paid API call',
                'database': 'pytest isolated test database', 'source': source,
                'tools': result.tool_invocations}
    # IDs refer only to disposable test rows and no student content is included.
    Path('tests/evaluation/wikipedia_agent_live.json').write_text(json.dumps(evidence, ensure_ascii=False, indent=2)+'\n')
