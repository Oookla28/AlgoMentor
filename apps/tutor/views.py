from dataclasses import asdict
from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from core.http import api_endpoint,json_body
from apps.knowledge.models import KnowledgePoint
from .models import ChatSession,TeachingSession
from .services.chat_service import answer,advance_teaching

@login_required
def chat(request):
    from apps.problems.models import Problem
    problem=Problem.objects.filter(pk=request.GET.get('problem'),is_active=True).first() if request.GET.get('problem','').isdigit() else None
    sessions=ChatSession.objects.filter(user=request.user)
    session=sessions.filter(pk=request.GET.get('session')).first() if request.GET.get('session','').isdigit() else None
    return render(request,'tutor/chat.html',{'teaching':TeachingSession.objects.filter(user=request.user,chat_session=session).first() if session else None,'problem':problem,'sessions':sessions,'selected_session':session,'chat_messages':session.messages.all() if session else [],'point':KnowledgePoint.objects.filter(slug=request.GET.get('point','')).first(),'page_title':'AI 智能助教'})

@api_endpoint(methods=('POST',))
def chat_api(request):
    data=json_body(request)
    result=answer(request.user,data.get('message',''),data.get('session_id'),data.get('tier'),data.get('mode','explain'),data.get('point'),data.get('problem_id'))
    payload=asdict(result)
    payload['answer']=result.text
    return payload

@api_endpoint()
def sessions_api(request):
    return {'sessions':list(ChatSession.objects.filter(user=request.user).values('id','title','updated_at'))}

@api_endpoint()
def session_api(request,session_id):
    session=ChatSession.objects.get(pk=session_id,user=request.user)
    import uuid
    from apps.agents.models import AgentTrace
    from apps.agents.services.trace_service import serialize_trace
    messages=list(session.messages.values('id','role','content','citations','trace_id','status','created_at'))
    for item in messages:
        item['tool_invocations']=[]
        if item['trace_id']:
            try: trace_id=uuid.UUID(item['trace_id'])
            except (ValueError,TypeError): continue
            trace=AgentTrace.objects.filter(pk=trace_id,user=request.user).first()
            if trace: item['tool_invocations']=serialize_trace(trace)['tool_invocations']
    teaching=TeachingSession.objects.filter(chat_session=session,user=request.user).first()
    return {'id':session.id,'title':session.title,'messages':messages,'teaching':{'level':teaching.current_level,'status':teaching.current_status,'mode':teaching.teaching_mode} if teaching else None}

@api_endpoint(methods=('POST',))
def teaching_api(request,session_id):
    return advance_teaching(request.user,session_id,json_body(request).get('action'))
