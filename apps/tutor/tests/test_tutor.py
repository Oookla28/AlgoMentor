import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from apps.tutor.models import ChatSession,TeachingSession
from apps.tutor.services.chat_service import advance_teaching

@pytest.mark.django_db
def test_sessions_isolated_and_logout_revokes_access():
    a=get_user_model().objects.create_user('alice',password='a-safe-password')
    b=get_user_model().objects.create_user('bob',password='b-safe-password')
    session=ChatSession.objects.create(user=b,title='private')
    client=Client();client.force_login(a)
    assert client.get(f'/api/v1/chat/sessions/{session.pk}/').status_code==404
    client.logout()
    assert client.get('/api/v1/chat/sessions/').status_code==401

@pytest.mark.django_db
def test_hint_stage_persists_and_cannot_access_other_user():
    a=get_user_model().objects.create_user('alice')
    b=get_user_model().objects.create_user('bob')
    chat=ChatSession.objects.create(user=a)
    TeachingSession.objects.create(user=a,chat_session=chat)
    assert advance_teaching(a,chat.pk,'hint')['level']==2
    with pytest.raises(TeachingSession.DoesNotExist): advance_teaching(b,chat.pk,'hint')
    assert advance_teaching(a,chat.pk,'end')['status']=='COMPLETED'

@pytest.mark.django_db
def test_hint_requests_do_not_claim_delivered_hint():
    user=get_user_model().objects.create_user('pending-hint')
    chat=ChatSession.objects.create(user=user)
    teaching=TeachingSession.objects.create(user=user,chat_session=chat)
    advance_teaching(user,chat.pk,'hint')
    teaching.refresh_from_db()
    assert teaching.current_level==2
    assert teaching.provided_hints==[]

@pytest.mark.django_db
def test_history_returns_real_trace_and_persisted_teaching_state():
    from apps.tutor.models import ChatMessage
    from apps.agents.models import AgentTrace,ToolInvocation
    user=get_user_model().objects.create_user('trace-history')
    chat=ChatSession.objects.create(user=user)
    TeachingSession.objects.create(user=user,chat_session=chat,current_level=3,teaching_mode='socratic')
    trace=AgentTrace.objects.create(user=user,session_id=str(chat.pk),selected_model='deepseek-flash',tier='fast')
    ToolInvocation.objects.create(trace=trace,tool_name='get_current_time',status='SUCCESS')
    ChatMessage.objects.create(session=chat,role='assistant',content='Observed result',trace_id=str(trace.pk))
    client=Client();client.force_login(user)
    data=client.get(f'/api/v1/chat/sessions/{chat.pk}/').json()['data']
    assert data['teaching']['level']==3
    assert data['teaching']['mode']=='socratic'
    assert data['messages'][0]['tool_invocations'][0]['tool_name']=='get_current_time'
