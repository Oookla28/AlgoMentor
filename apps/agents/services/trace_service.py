import json,time
from collections import Counter
from django.conf import settings
from django.utils import timezone
from apps.agents.models import AgentTrace,ToolInvocation
from core.exceptions import BusinessError


class ToolBudget:
    def __init__(self,trace,deadline):
        self.trace=trace;self.deadline=deadline;self.calls=0;self.signatures=Counter()
        self.external_sources=[]

    def call(self,name,arguments,func):
        if time.monotonic()>self.deadline:
            raise BusinessError('智能体任务已超时。',code='AGENT_TIMEOUT',status_code=504)
        self.calls+=1
        signature=json.dumps([name,arguments],sort_keys=True,ensure_ascii=False)
        self.signatures[signature]+=1
        if self.calls>getattr(settings,'AGENT_MAX_TOOL_CALLS',8):
            raise BusinessError('智能体已达到本次工具调用上限。',code='TOOL_BUDGET_EXCEEDED',status_code=429)
        if self.signatures[signature]>2:
            raise BusinessError('检测到重复工具循环，已停止。',code='TOOL_LOOP_DETECTED',status_code=422)
        # Only argument names and sizes; neither code nor user text is persisted.
        summary=', '.join(f'{key}: {len(str(value))} 字符' for key,value in arguments.items()) or '无参数'
        row=ToolInvocation.objects.create(trace=self.trace,tool_name=name,input_summary=summary[:500])
        started=time.monotonic()
        try:
            result=func(**arguments)
            if time.monotonic()>self.deadline:
                raise BusinessError('智能体任务已超时。',code='AGENT_TIMEOUT',status_code=504)
            row.status='SUCCESS'
            if name in ('search_wikipedia','search_external_knowledge') and isinstance(result,dict):
                if result.get('success') and result.get('source_type')=='wikipedia':
                    if not any(source.get('source_url')==result.get('source_url') for source in self.external_sources):
                        self.external_sources.append(result)
                elif result.get('query_status')=='UNAVAILABLE':
                    row.status='FAILED';row.error_type=str(result.get('error_code') or 'EXTERNAL_KNOWLEDGE_UNAVAILABLE')[:80]
            row.output_summary=f'真实工具返回，{len(str(result))} 字符'
            return result
        except Exception as exc:
            row.status='FAILED';row.error_type=getattr(exc,'code',type(exc).__name__)[:80]
            raise
        finally:
            row.duration_ms=int((time.monotonic()-started)*1000)
            row.save(update_fields=['duration_ms','status','error_type','output_summary'])


def serialize_trace(trace):
    return {'id':str(trace.pk),'session_id':trace.session_id,'selected_model':trace.selected_model,'tier':trace.tier,'status':trace.status,'duration_ms':trace.duration_ms,'error_type':trace.error_type,'started_at':trace.started_at.isoformat(),'tool_invocations':[{'id':row.pk,'tool_name':row.tool_name,'input_summary':row.input_summary,'status':row.status,'duration_ms':row.duration_ms,'error_type':row.error_type} for row in trace.invocations.all()]}
