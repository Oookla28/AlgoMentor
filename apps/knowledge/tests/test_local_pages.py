"""UI/API integration uses local records and injected HTTP results, never paid AI."""
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.test import TestCase
from core.exceptions import KnowledgeRetrievalError, ValidationError


class LocalLearningEntryTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='local-reader', password='test-password')
        self.client.force_login(self.user)

    def test_entry_pages_are_available_without_api_key(self):
        with patch('requests.sessions.Session.request', side_effect=AssertionError('entry page must not request external HTTP')):
            for path in ['/knowledge/local/', '/knowledge/wikipedia/', '/knowledge/', '/graph/', '/visualizations/', '/learning/', '/mistakes/']:
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200, path)
        page = self.client.get('/knowledge/local/').content.decode()
        self.assertIn('本地检索模式', page)
        self.assertIn('不调用 DeepSeek', page)
        self.assertNotIn('localStorage', page)

    def test_local_search_does_not_request_ai_or_live_wikipedia(self):
        cache = {'success': True, 'source_type': 'wikipedia', 'title': '红黑树', 'summary': '缓存测试摘要', 'from_cache': True, 'cache_status': 'STALE'}
        citation = {'source_type': 'original', 'chunk_id': 'real-course-chunk', 'content': '课程原文', 'page_number': 3}
        with patch('apps.knowledge.views.retrieve_knowledge', return_value=[]), patch('apps.knowledge.views.citations_json', return_value=[citation]), patch('apps.knowledge.services.wikipedia_service.search_wikipedia', return_value=cache) as wiki, patch('requests.sessions.Session.request', side_effect=AssertionError('local entry must not request HTTP')):
            response = self.client.get('/api/v1/knowledge/local/', {'q': '红黑树'})
        self.assertEqual(response.status_code, 200)
        data = response.json()['data']
        self.assertEqual(data['mode'], 'LOCAL_RETRIEVAL')
        self.assertFalse(data['generated_by_ai'])
        self.assertEqual(data['citations'], [citation])
        self.assertTrue(data['wikipedia']['from_cache'])
        wiki.assert_called_once_with('红黑树', language='zh', cache_only=True)

    def test_missing_local_embedding_keeps_cached_evidence(self):
        cached = {'success': True, 'title': 'KMP', 'from_cache': True}
        with patch('apps.knowledge.views.retrieve_knowledge', side_effect=KnowledgeRetrievalError('本地模型未准备好。')), patch('apps.knowledge.services.wikipedia_service.search_wikipedia', return_value=cached):
            response = self.client.get('/api/v1/knowledge/local/', {'q': 'KMP'})
        self.assertEqual(response.status_code, 200)
        data = response.json()['data']
        self.assertIn('未准备好', data['retrieval_error'])
        self.assertEqual(data['citations'], [])
        self.assertTrue(data['wikipedia']['success'])

    def test_private_or_long_course_question_retains_local_evidence(self):
        citation = {'content': '课程中的相关证据', 'page_number': 2}
        with patch('apps.knowledge.views.retrieve_knowledge', return_value=[]), patch('apps.knowledge.views.citations_json', return_value=[citation]), patch('apps.knowledge.services.wikipedia_service.search_wikipedia', side_effect=ValidationError('只接受公开概念。', code='PUBLIC_CONCEPT_REQUIRED')):
            response = self.client.get('/api/v1/knowledge/local/', {'q': '请根据我已有的课程学习进度，说明如何理解广义表。'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['data']['citations'], [citation])
        self.assertFalse(response.json()['data']['wikipedia']['success'])

    def test_standalone_wikipedia_needs_no_deepseek(self):
        result = {'success': True, 'source_type': 'wikipedia', 'summary': 'test', 'from_cache': False}
        with patch('apps.knowledge.services.wikipedia_service.search_wikipedia', return_value=result) as wiki:
            response = self.client.get('/api/v1/knowledge/wikipedia/', {'q': 'KMP', 'language': 'en', 'refresh': '1'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['data']['result'], result)
        wiki.assert_called_once_with('KMP', language='en', force_refresh=True, cache_only=False)

    def test_cache_only_and_failures_are_explicit_data(self):
        result = {'success': False, 'error': '本地没有此词条缓存。', 'cache_status': 'MISS'}
        with patch('apps.knowledge.services.wikipedia_service.search_wikipedia', return_value=result) as wiki:
            response = self.client.get('/api/v1/knowledge/wikipedia/', {'q': '红黑树', 'cache_only': '1'})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()['data']['result']['success'])
        wiki.assert_called_once_with('红黑树', language='zh', force_refresh=False, cache_only=True)

    def test_queries_require_authentication_and_validation(self):
        for path in ['/api/v1/knowledge/local/', '/api/v1/knowledge/wikipedia/']:
            self.assertEqual(self.client.get(path).status_code, 400)
            self.assertEqual(self.client.get(path, {'q': 'x' * 1001}).status_code, 400)
            self.assertEqual(self.client.get(path, {'q': 'KMP', 'language': 'invalid'}).status_code, 400)
        self.client.logout()
        self.assertEqual(self.client.get('/api/v1/knowledge/wikipedia/', {'q': 'KMP'}).status_code, 401)
        self.assertEqual(self.client.get('/knowledge/local/').status_code, 302)

    def test_status_reads_do_not_probe_any_external_provider(self):
        with patch('requests.sessions.Session.request', side_effect=AssertionError('status should only read local state')):
            response = self.client.get('/api/v1/services/status/')
        self.assertEqual(response.status_code, 200)
        services = response.json()['data']['services']
        self.assertEqual({row['service'] for row in services}, {'deepseek', 'wikipedia', 'code_execution'})
        self.assertTrue(all(row['status'] == 'UNKNOWN' for row in services))

    def test_status_keeps_personal_key_error_private(self):
        from core.services.availability import ServiceAvailabilityManager
        ServiceAvailabilityManager('deepseek', user=self.user).record_failure('INVALID_API_KEY')
        own = self.client.get('/api/v1/services/status/').json()['data']['services']
        self.assertEqual(next(row for row in own if row['service'] == 'deepseek')['error_code'], 'INVALID_API_KEY')
        another = get_user_model().objects.create_user(username='other-status-reader')
        self.client.force_login(another)
        other = self.client.get('/api/v1/services/status/').json()['data']['services']
        self.assertEqual(next(row for row in other if row['service'] == 'deepseek')['status'], 'UNKNOWN')

    def test_single_model_failure_does_not_block_other_chat_tier(self):
        from core.services.availability import ServiceAvailabilityManager
        ServiceAvailabilityManager('deepseek', user=self.user, model='deepseek-v4-pro').record_failure('MODEL_UNAVAILABLE')
        expert = self.client.get('/api/v1/services/status/', {'tier': 'expert'}).json()['data']['services']
        fast = self.client.get('/api/v1/services/status/', {'tier': 'fast'}).json()['data']['services']
        self.assertFalse(next(row for row in expert if row['service'] == 'deepseek')['can_attempt'])
        self.assertTrue(next(row for row in fast if row['service'] == 'deepseek')['can_attempt'])
        self.assertEqual(self.client.get('/api/v1/services/status/', {'tier': 'invalid'}).status_code, 400)


import pytest


@pytest.mark.django_db
def test_configured_default_wikipedia_language_is_used_when_not_supplied(settings, client):
    settings.WIKIPEDIA_DEFAULT_LANGUAGE = 'en'
    user = get_user_model().objects.create_user('configured-language-reader')
    client.force_login(user)
    with patch('apps.knowledge.services.wikipedia_service.search_wikipedia', return_value={'success': False}) as search:
        response = client.get('/api/v1/knowledge/wikipedia/', {'q': 'Treap'})
    assert response.status_code == 200
    assert search.call_args.kwargs['language'] == 'en'
    page = client.get('/knowledge/wikipedia/').content.decode()
    assert 'value="en" selected' in page
