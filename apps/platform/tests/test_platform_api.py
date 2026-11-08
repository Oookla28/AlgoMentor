import time

import pytest
from django.core.cache import cache
from django.test import Client

from apps.platform.agent.state_machine import AgentOutcome
from apps.platform.models import AgentRun


def _staff(django_user_model):
    return django_user_model.objects.create_user('platform-staff', password='test-password', is_staff=True)


def _student(django_user_model, name='platform-student'):
    return django_user_model.objects.create_user(name, password='test-password')


@pytest.fixture
def fake_capabilities(monkeypatch):
    monkeypatch.setattr('apps.platform.views.probe_capabilities', lambda: [
        {'name': 'django', 'state': 'available', 'reason': '', 'details': {'version': '5.2.14'}},
        {'name': 'piston', 'state': 'environment-limited', 'reason': 'localhost_2000_not_open', 'details': {}},
    ])


@pytest.mark.django_db
def test_capability_api_is_staff_only(client, django_user_model, fake_capabilities):
    student = _student(django_user_model)
    client.force_login(student)
    assert client.get('/api/v1/platform/capabilities/').status_code == 403
    client.force_login(_staff(django_user_model))
    response = client.get('/api/v1/platform/capabilities/')
    assert response.status_code == 200
    payload = response.json()['data']
    assert {item['name'] for item in payload['capabilities']} == {'django', 'piston'}
    assert payload['domain_packs']


@pytest.mark.django_db
def test_console_page_hides_from_students_and_renders_for_staff(client, django_user_model, fake_capabilities):
    student = _student(django_user_model)
    client.force_login(student)
    assert client.get('/platform/').status_code == 403
    client.force_login(_staff(django_user_model))
    response = client.get('/platform/')
    assert response.status_code == 200
    body = response.content.decode()
    assert '平台能力与 Agent 控制台' in body
    assert 'Capability Health' in body
    assert 'data_structures' in body


@pytest.mark.django_db
def test_agent_run_api_returns_serialized_run(client, django_user_model, monkeypatch):
    staff = _staff(django_user_model)
    client.force_login(staff)

    def fake_run(user, query, domain='data_structures', mode='adaptive'):
        run = AgentRun.objects.create(
            run_id='run-api-1', user=user, domain=domain, query=query, status='COMPLETED',
            answer_text='根据检索到的课程证据：[来源1] 测试。', citations=[], metrics={'gate': {'decision': 'PASS'}},
        )
        return AgentOutcome('run-api-1', 'COMPLETED', run.answer_text, [], 0, 0, run.metrics)

    monkeypatch.setattr('apps.platform.views.run_evidence_agent', fake_run)
    response = client.post('/api/v1/platform/agent/run/',
                           data='{"query":"循环队列判满条件","domain":"data_structures"}',
                           content_type='application/json')
    assert response.status_code == 200, response.content
    payload = response.json()['data']
    assert payload['run_id'] == 'run-api-1'
    assert payload['status'] == 'COMPLETED'
    assert payload['answer'].startswith('根据检索到的课程证据')


@pytest.mark.django_db
def test_agent_run_api_validates_domain(client, django_user_model):
    client.force_login(_student(django_user_model))
    response = client.post('/api/v1/platform/agent/run/',
                           data='{"query":"测试","domain":"missing"}',
                           content_type='application/json')
    assert response.status_code == 400
    assert response.json()['error']['code'] == 'DOMAIN_PACK_NOT_FOUND'


@pytest.mark.django_db
def test_agent_run_rate_limit(client, django_user_model):
    user = _student(django_user_model)
    client.force_login(user)
    key = f'platform-agent-rate:{user.pk}:{int(time.time() // 60)}'
    cache.set(key, 10, 70)
    response = client.post('/api/v1/platform/agent/run/',
                           data='{"query":"循环队列"}', content_type='application/json')
    assert response.status_code == 429
    assert response.json()['error']['code'] == 'RATE_LIMITED'


@pytest.mark.django_db
def test_agent_run_requires_csrf(django_user_model):
    client = Client(enforce_csrf_checks=True)
    client.force_login(_staff(django_user_model))
    response = client.post('/api/v1/platform/agent/run/',
                           data='{"query":"循环队列"}', content_type='application/json')
    assert response.status_code == 403


@pytest.mark.django_db
def test_run_detail_is_owner_or_staff(client, django_user_model):
    owner = _student(django_user_model, 'run-owner')
    other = _student(django_user_model, 'run-other')
    run = AgentRun.objects.create(run_id='run-owner-1', user=owner, query='循环队列', status='COMPLETED')
    client.force_login(other)
    assert client.get('/api/v1/platform/runs/run-owner-1/').status_code == 403
    client.force_login(owner)
    assert client.get('/api/v1/platform/runs/run-owner-1/').status_code == 200
    client.force_login(_staff(django_user_model))
    assert client.get('/api/v1/platform/runs/run-owner-1/').status_code == 200
    assert client.get('/api/v1/platform/runs/run-owner-1/').json()['data']['run_id'] == run.run_id
