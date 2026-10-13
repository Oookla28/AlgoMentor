import time
from dataclasses import dataclass,field
from django.conf import settings
from django.utils import timezone
from apps.accounts.services.credential_service import get_config,get_api_key
from apps.agents.models import AgentTrace
from apps.agents.services.agent_factory import create_tutor_agent
from apps.agents.services.trace_service import ToolBudget,serialize_trace
from core.llm.deepseek_client import DeepSeekClient
from core.llm.model_registry import get_tier
from core.security.permissions import require_user
from core.exceptions import BusinessError,ValidationError


@dataclass(frozen=True)
class AgentResult:
    text: str
    trace_id: str
    tool_invocations: list[dict] = field(default_factory=list)


def run_agent(user,message: str,session_id=None,tier=None,history=None,client=None,system_prompt=None) -> AgentResult:
    require_user(user)
    if not isinstance(message,str) or not message.strip() or len(message)>20000:
        raise ValidationError('请输入有效且不超过 20000 字符的问题。')
    if session_id:
        from apps.tutor.models import ChatSession
        ChatSession.objects.get(pk=session_id,user=user)
    get_api_key(user)
    selected=get_tier(tier or get_config(user).default_tier)
    trace=AgentTrace.objects.create(user=user,session_id=str(session_id or ''),selected_model=selected.model,tier=selected.key)
    started=time.monotonic();deadline=started+getattr(settings,'AGENT_TIMEOUT',90)
    budget=ToolBudget(trace,deadline)
    client=client or DeepSeekClient(user,purpose='agent',deadline=deadline)
    try:
        agent=create_tutor_agent(user,client,selected.key,budget,system_prompt=system_prompt)
        messages=list(history or [])[-20:]+[{'role':'user','content':message}]
        result=agent.invoke({'messages':messages},config={'recursion_limit':2*getattr(settings,'AGENT_MAX_TOOL_CALLS',8)+3,'max_concurrency':1})
        if time.monotonic()>deadline:
            raise BusinessError('智能体任务已超时。',code='AGENT_TIMEOUT',status_code=504)
        final=result['messages'][-1]
        if not getattr(final,'content','') or getattr(final,'tool_calls',None):
            raise BusinessError('智能体未完成回答，请缩小问题范围。',code='AGENT_INCOMPLETE',status_code=502)
        trace.status='SUCCESS'
        return AgentResult(str(final.content),str(trace.pk),serialize_trace(trace)['tool_invocations'])
    except BusinessError as exc:
        trace.status='TIMEOUT' if 'TIMEOUT' in exc.code else 'FAILED';trace.error_type=exc.code
        raise
    except Exception as exc:
        trace.status='FAILED';trace.error_type=type(exc).__name__
        raise BusinessError('智能体任务执行失败，请重试或查看工具记录。',code='AGENT_FAILED',status_code=502) from None
    finally:
        trace.finished_at=timezone.now();trace.duration_ms=int((time.monotonic()-started)*1000)
        trace.save(update_fields=['status','error_type','finished_at','duration_ms'])
