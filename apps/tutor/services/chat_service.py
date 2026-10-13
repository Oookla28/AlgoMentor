from dataclasses import dataclass,field
import re
from django.db import transaction
from django.utils import timezone
from core.exceptions import ValidationError,BusinessError
from apps.tutor.models import ChatSession,ChatMessage,TeachingSession
from apps.knowledge.models import KnowledgePoint
from apps.knowledge.services.retrieval_service import retrieve_knowledge,citations_json,verified_citation_ids
from .prompt_service import MODES,teaching_prompt

@dataclass(frozen=True)
class ChatResponse:
    session_id: int
    message_id: int
    text: str
    citations: list
    trace_id: str
    tool_invocations: list
    external_sources: list = field(default_factory=list)


def answer(user,message,session_id=None,tier=None,mode='explain',point=None,problem_id=None):
    if not isinstance(message,str) or not message.strip() or len(message)>6000: raise ValidationError('问题须为 1 至 6000 字。')
    if mode not in MODES: raise ValidationError('教学模式无效。')
    from apps.accounts.services.credential_service import get_api_key
    get_api_key(user) # Validate BYOK before creating failed messages.
    if session_id:
        if not isinstance(session_id,(int,str)) or not str(session_id).isdigit(): raise ValidationError('会话编号无效。')
        session=ChatSession.objects.get(pk=session_id,user=user)
    else:
        session=ChatSession.objects.create(user=user,title=message[:50])
    teaching,_=TeachingSession.objects.get_or_create(user=user,chat_session=session)
    teaching.teaching_mode=mode
    if problem_id is not None:
        from apps.problems.models import Problem
        if not str(problem_id).isdigit(): raise ValidationError('题目编号无效。')
        teaching.problem=Problem.objects.get(pk=problem_id,is_active=True)
        teaching.current_objective=teaching.problem.title
    if point:
        teaching.knowledge_point=KnowledgePoint.objects.get(slug=point)
        teaching.current_objective=teaching.knowledge_point.name
    if teaching.current_status!='ACTIVE': raise ValidationError('此教学会话已结束，请创建新会话。')
    teaching.last_student_response=message
    teaching.save()
    prior=list(session.messages.filter(status='SUCCESS').values('role','content'))[-12:]
    incoming=ChatMessage.objects.create(session=session,role='user',content=message)
    try:
        try: evidence=retrieve_knowledge(message)
        except BusinessError as exc:
            if exc.code=='INDEX_MISSING': evidence=[]
            else: raise
        from apps.agents.services.agent_service import run_agent
        from apps.knowledge.services.wikipedia_service import extract_public_concept,normalize_query
        explicit_wikipedia='维基百科' in message or 'wikipedia' in message.casefold()
        concept_question=bool(re.search(r'什么是|解释|介绍|定义|原理|复杂度|算法如何|算法是什么|what is|explain',message,re.I))
        wikipedia_query=extract_public_concept(message) if explicit_wikipedia or (not evidence and concept_question) else None
        if wikipedia_query is None and (explicit_wikipedia or (not evidence and concept_question)):
            try:wikipedia_query=normalize_query(message)
            except ValidationError:pass  # Never send an unsafe/private full question to Wikipedia.
        result=run_agent(user,message,session_id=session.pk,tier=tier,history=prior,system_prompt=teaching_prompt(teaching,evidence),wikipedia_query=wikipedia_query)
        cited=verified_citation_ids(result.text,evidence)
        sources=citations_json(cited)
        # Keep independent evidence visible even if model failed to attach an inline reference.
        if evidence and not cited:
            sources=citations_json(evidence)
        external_sources=getattr(result,'external_sources',[])
        sources+=external_sources
        with transaction.atomic():
            outgoing=ChatMessage.objects.create(session=session,role='assistant',content=result.text,citations=sources,trace_id=str(result.trace_id))
            session.updated_at=timezone.now();session.save(update_fields=['updated_at'])
            if teaching.current_level > 1:
                teaching.provided_hints=[*teaching.provided_hints,{'level':teaching.current_level,'at':timezone.now().isoformat(),'message_id':outgoing.pk}]
                teaching.save(update_fields=['provided_hints'])
        return ChatResponse(session.pk,outgoing.pk,result.text,sources,str(result.trace_id),result.tool_invocations,external_sources)
    except Exception:
        incoming.status='FAILED';incoming.save(update_fields=['status'])
        raise


def advance_teaching(user,session_id,action):
    teaching=TeachingSession.objects.get(user=user,chat_session_id=session_id)
    if action=='hint':
        teaching.current_level=min(4,teaching.current_level+1)
    elif action=='full':
        teaching.current_level=4
    elif action=='restart':
        teaching.current_level=1;teaching.current_status='ACTIVE';teaching.provided_hints=[]
    elif action=='end': teaching.current_status='COMPLETED'
    else: raise ValidationError('无效的教学操作。')
    teaching.save()
    return {'level':teaching.current_level,'status':teaching.current_status}
