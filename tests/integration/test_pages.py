import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.core.management import call_command
from apps.problems.models import Problem

@pytest.mark.django_db
def test_all_pages_render_with_real_empty_account():
    call_command('seed_knowledge');call_command('seed_problems')
    user=get_user_model().objects.create_user('page-test',password='test-only-strong')
    client=Client();client.force_login(user)
    for path in ['/','/tutor/','/accounts/settings/','/knowledge/','/graph/','/visualizations/','/problems/','/lab/','/learning/','/mistakes/','/reports/']:
        response=client.get(path)
        assert response.status_code==200,(path,response.status_code)
        assert b'Traceback' not in response.content
    assert client.get(f'/problems/{Problem.objects.first().slug}/').status_code==200
    data=client.get('/api/v1/learning/summary/').json()['data']
    assert data['total_submissions']==0
    assert data['submission_accuracy'] is None
    assert all(p['evidence_count']==0 for p in data['knowledge_mastery'])

@pytest.mark.django_db
def test_ai_unconfigured_is_explicit_and_not_fake_success():
    user=get_user_model().objects.create_user('no-key')
    client=Client();client.force_login(user)
    response=client.post('/api/v1/chat/',{'message':'现在几点？'},content_type='application/json')
    assert response.status_code==428
    assert response.json()['error']['code']=='API_KEY_REQUIRED'
    assert client.post('/api/report/',{},content_type='application/json').status_code==428
