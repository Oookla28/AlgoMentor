import time
from unittest.mock import Mock
from cryptography.fernet import Fernet
import pytest
from django.contrib.auth.models import User
from django.utils import timezone
from apps.accounts.services.credential_service import save_config
from apps.agents.models import AgentTrace,ToolInvocation
from apps.agents.services.agent_service import run_agent
from apps.agents.services.trace_service import ToolBudget
from apps.agents.services.tool_registry import build_tools
from apps.agents.tools.current_time_tool import current_time
from apps.agents.tools.external_search_tool import WikipediaProvider
from core.exceptions import BusinessError
from core.llm.provider import LLMResult,TokenUsage
from core.llm.langchain_adapter import DeepSeekChatModel,serialize_message
from langchain_core.messages import HumanMessage,ToolMessage

pytestmark=pytest.mark.django_db(transaction=True)

@pytest.fixture
def user(settings):
    settings.APP_ENCRYPTION_KEY=Fernet.generate_key().decode()
    student=User.objects.create_user('student');save_config(student,'sk-test-key-12345678',default_tier='deep');return student


class ToolClient:
    def __init__(self): self.calls=[]
    def complete(self,messages,**kwargs):
        self.calls.append((messages,kwargs))
        if len(self.calls)==1:
            return LLMResult('',TokenUsage(10,5,15),'deepseek-flash',({'id':'clock-1','type':'function','function':{'name':'get_current_time','arguments':'{}'}},),'internal reasoning to preserve','tool_calls')
        assert any(message.get('reasoning_content')=='internal reasoning to preserve' for message in messages)
        assert any(message['role']=='tool' for message in messages)
        return LLMResult('已查询真实系统时间。',TokenUsage(20,5,25),'deepseek-flash',finish_reason='stop')


def test_real_langchain_agent_calls_real_clock_preserves_reasoning(user):
    client=ToolClient()
    result=run_agent(user,'现在几点',client=client)
    assert result.text=='已查询真实系统时间。'
    assert len(client.calls)==2
    trace=AgentTrace.objects.get(pk=result.trace_id)
    assert trace.status=='SUCCESS'
    invocation=ToolInvocation.objects.get(trace=trace)
    assert invocation.tool_name=='get_current_time' and invocation.status=='SUCCESS'
    assert 'internal reasoning' not in str(result.tool_invocations)


def test_agent_multi_tool_real_db_and_clock(user):
    class MultiClient(ToolClient):
        def complete(self,messages,**kwargs):
            self.calls.append((messages,kwargs))
            if len(self.calls)==1:
                return LLMResult('',TokenUsage(),'deepseek-flash',({'id':'learn','type':'function','function':{'name':'query_student_learning','arguments':'{"days":7}'}},{'id':'clock','type':'function','function':{'name':'get_current_time','arguments':'{}'}}),'reason','tool_calls')
            assert sum(message['role']=='tool' for message in messages)==2
            return LLMResult('当前没有有效提交。',TokenUsage(),'deepseek-flash')
    result=run_agent(user,'查询我的学习统计与现在时间',client=MultiClient())
    assert len(result.tool_invocations)==2 and all(row['status']=='SUCCESS' for row in result.tool_invocations)


def test_current_time_uses_clock():
    result=current_time()
    assert result['date']==timezone.localdate().isoformat() and '+08:00' in result['iso8601']


def test_tool_schema_cannot_inject_student_id(user):
    trace=AgentTrace.objects.create(user=user,selected_model='deepseek-flash',tier='deep')
    tool=next(tool for tool in build_tools(user,ToolBudget(trace,time.monotonic()+10)) if tool.name=='query_student_learning')
    with pytest.raises(ValueError): tool.invoke({'days':7,'student_id':999})
    assert not trace.invocations.exists()


def test_repeated_tool_loop_and_deadline(user):
    trace=AgentTrace.objects.create(user=user,selected_model='deepseek-flash',tier='deep')
    budget=ToolBudget(trace,time.monotonic()+10)
    assert budget.call('clock',{},current_time)
    assert budget.call('clock',{},current_time)
    with pytest.raises(BusinessError) as exc: budget.call('clock',{},current_time)
    assert exc.value.code=='TOOL_LOOP_DETECTED'
    with pytest.raises(BusinessError) as exc: ToolBudget(trace,time.monotonic()-1).call('clock',{},current_time)
    assert exc.value.code=='AGENT_TIMEOUT'


def test_tools_only_trace_summary(user):
    trace=AgentTrace.objects.create(user=user,selected_model='deepseek-flash',tier='deep')
    budget=ToolBudget(trace,time.monotonic()+10)
    budget.call('test',{'code':'sk-test-key-12345678'},lambda code:{'text':code})
    row=ToolInvocation.objects.get(trace=trace)
    assert 'sk-test-key' not in row.input_summary+row.output_summary


def test_wikipedia_real_transport_contract():
    # The existing contract now exercises the official Action API's search then
    # page-extract flow rather than the older REST exact-title-only endpoint.
    transport=Mock()
    import json
    search=Mock(status_code=200,headers={});search.iter_content.return_value=[json.dumps({'query':{'search':[{'title':'红黑树','pageid':55999,'ns':0}]}}).encode()]
    article=Mock(status_code=200,headers={});article.iter_content.return_value=[json.dumps({'query':{'pages':[{'title':'红黑树','pageid':55999,'ns':0,'extract':'一种自平衡二叉搜索树','canonicalurl':'https://zh.wikipedia.org/wiki/红黑树','revisions':[{'revid':123}]}]}}).encode()]
    transport.get.side_effect=[search,article]
    result=WikipediaProvider(transport).search('红黑树')
    assert result['found'] and result['extract']=='一种自平衡二叉搜索树'
    assert result['success'] and result['page_id']==55999 and result['revision_id']==123
    assert transport.get.call_args_list[0].kwargs['params']['list']=='search'
    for call in transport.get.call_args_list:
        assert call.args[0]=='https://zh.wikipedia.org/w/api.php'
        assert call.kwargs['allow_redirects'] is False


def test_foreign_chat_session_rejected(user):
    from apps.tutor.models import ChatSession
    other=User.objects.create_user('other');session=ChatSession.objects.create(user=other,title='Private')
    with pytest.raises(ChatSession.DoesNotExist): run_agent(user,'偷看',session_id=session.pk,client=ToolClient())
    assert not AgentTrace.objects.exists()
