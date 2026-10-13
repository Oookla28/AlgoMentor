from datetime import timedelta
from io import StringIO
import hashlib
import json
from unittest.mock import Mock

import pytest
import requests
from django.core.management import call_command
from django.utils import timezone

from apps.knowledge.models import WikipediaCache
from apps.knowledge.services.wikipedia_service import (
    MediaWikiClient, extract_public_concept, normalize_query, normalized_title, search_wikipedia,
)
from core.exceptions import ExternalServiceError, ValidationError
from core.services.availability import ServiceAvailabilityManager

pytestmark = pytest.mark.django_db


def response(value, status=200):
    result = Mock(status_code=status, headers={})
    result.json.return_value = value
    result.iter_content.return_value = [json.dumps(value, ensure_ascii=False).encode('utf-8')]
    return result


def search_response(*titles):
    return response({'query': {'search': [{'pageid': index, 'title': title, 'ns': 0} for index, title in enumerate(titles, 1)]}})


def article_response(title='红黑树', **overrides):
    article = {'title': title, 'pageid': 1, 'ns': 0, 'extract': '真实 API 样式测试摘要（测试夹具）。', 'canonicalurl': f'https://zh.wikipedia.org/wiki/{title}', 'revisions': [{'revid': 42}]}
    article.update(overrides)
    return response({'query': {'pages': [article]}})


def transport_for(*responses):
    transport = Mock()
    transport.get.side_effect = responses
    return transport


def cache_article(*, language='zh', title='红黑树', expired=False):
    retrieved = timezone.now() - timedelta(days=10 if expired else 1)
    summary = '历史公开百科摘要（测试夹具）。'
    return WikipediaCache.objects.create(query=title, normalized_query=normalized_title(title), language=language, page_id=1, title=title, summary=summary, source_url=f'https://{language}.wikipedia.org/wiki/{title}', revision_id=40, retrieved_at=retrieved, expires_at=retrieved + timedelta(days=7), last_accessed_at=retrieved, content_hash=hashlib.sha256(summary.encode()).hexdigest())


def test_search_then_extract_persists_real_metadata_and_old_contract():
    transport = transport_for(search_response('红黑树'), article_response())
    result = search_wikipedia('什么是红黑树？', transport=transport)
    assert result['success'] and result['found'] and not result['from_cache']
    assert result['query'] == '红黑树' and result['summary'] == result['extract']
    assert result['page_id'] == 1 and result['revision_id'] == 42 and result['query_status'] == 'LIVE'
    assert result['source_url'] == result['url'] == 'https://zh.wikipedia.org/wiki/红黑树'
    assert 'oldid=42' in result['revision_url'] and result['license'] == 'CC BY-SA 4.0'
    row = WikipediaCache.objects.get()
    assert row.query == row.title == '红黑树' and row.content_hash == hashlib.sha256(result['summary'].encode()).hexdigest()
    assert row.retrieved_at.isoformat() == result['retrieved_at']
    assert (row.expires_at - row.retrieved_at).days == 7
    assert transport.get.call_args_list[0].kwargs['params']['list'] == 'search'
    assert 'extracts' in transport.get.call_args_list[1].kwargs['params']['prop']
    assert all(call.args[0] == 'https://zh.wikipedia.org/w/api.php' and not call.kwargs['allow_redirects'] for call in transport.get.call_args_list)


def test_title_relevance_chooses_exact_match_instead_of_first_result():
    transport = transport_for(search_response('左倾红黑树', '红黑树'), article_response())
    result = search_wikipedia('红黑树', transport=transport)
    assert result['title'] == '红黑树'
    assert transport.get.call_args_list[1].kwargs['params']['pageids'].split('|')[0] == '2'


def test_unrelated_first_result_is_not_returned_or_cached():
    transport = transport_for(search_response('三体'), search_response('Three-body problem'))
    result = search_wikipedia('红黑树', transport=transport)
    assert not result['success'] and result['error_code'] == 'WIKIPEDIA_NOT_FOUND'
    assert not WikipediaCache.objects.exists()


def test_no_chinese_result_uses_reviewed_english_alias_and_marks_language():
    transport = transport_for(search_response(), search_response('Red–black tree'), article_response('Red–black tree', canonicalurl='https://en.wikipedia.org/wiki/Red%E2%80%93black_tree'))
    result = search_wikipedia('红黑树', transport=transport)
    assert result['success'] and result['language'] == 'en' and 'English Wikipedia' in result['source']
    assert transport.get.call_args_list[1].args[0] == 'https://en.wikipedia.org/w/api.php'
    assert transport.get.call_args_list[1].kwargs['params']['srsearch'] == 'Red-black tree'
    assert WikipediaCache.objects.get().query == 'Red–black tree'


@pytest.mark.parametrize('overrides', [{'pageprops': {'disambiguation': ''}}, {'extract': ''}, {'missing': True}, {'extract': None}, {'pageid': -1}, {'title': '量子力学'}])
def test_disambiguation_empty_missing_or_unrelated_pages_fail(overrides):
    transport = transport_for(search_response('红黑树'), article_response(**overrides))
    result = search_wikipedia('红黑树', language='en', transport=transport)
    assert not result['success'] and not WikipediaCache.objects.exists()


def test_redirect_resolved_page_preserves_actual_title_id_and_revision():
    transport = transport_for(search_response('哈希表'), article_response('散列表', pageid=99))
    result = search_wikipedia('哈希表', transport=transport)
    assert result['success'] and result['title'] == '散列表' and result['page_id'] == 99
    assert transport.get.call_args_list[1].kwargs['params']['redirects'] == 1


def test_missing_revision_is_none_not_fabricated():
    result = search_wikipedia('红黑树', transport=transport_for(search_response('红黑树'), article_response(revisions=[])))
    assert result['revision_id'] is None and result['revision_url'] == ''


def test_fresh_cache_no_network_and_original_timestamp():
    row = cache_article()
    transport = Mock()
    result = search_wikipedia('紅黑樹', transport=transport)
    assert result['from_cache'] and result['cache_status'] == 'FRESH'
    assert result['retrieved_at'] == row.retrieved_at.isoformat() and result['revision_id'] == 40
    transport.get.assert_not_called()
    row.refresh_from_db()
    assert row.last_accessed_at > row.retrieved_at
    assert ServiceAvailabilityManager('wikipedia').snapshot()['status'] == 'UNKNOWN'


def test_stale_cache_fallback_after_network_failure():
    row = cache_article(expired=True)
    result = search_wikipedia('红黑树', transport=transport_for(requests.ConnectionError(), requests.ConnectionError()))
    assert result['success'] and result['from_cache'] and result['cache_status'] == 'STALE'
    assert result['query_status'] == 'STALE_CACHE' and '历史缓存' in result['cache_warning']
    assert result['retrieved_at'] == row.retrieved_at.isoformat() and result['error_code'] == 'EXTERNAL_KNOWLEDGE_NETWORK_ERROR'


def test_force_refresh_bypasses_fresh_cache_and_updates_existing_article():
    row = cache_article()
    result = search_wikipedia('红黑树', force_refresh=True, transport=transport_for(search_response('红黑树'), article_response(revisions=[{'revid': 43}])))
    assert not result['from_cache'] and result['revision_id'] == 43
    assert WikipediaCache.objects.count() == 1
    row.refresh_from_db()
    assert row.revision_id == 43 and row.retrieved_at > timezone.now() - timedelta(seconds=5)


def test_force_refresh_failure_never_calls_cache_live():
    row = cache_article()
    result = search_wikipedia('红黑树', force_refresh=True, transport=transport_for(requests.Timeout(), requests.Timeout()))
    assert result['from_cache'] and result['query_status'] == 'CACHE' and '实时查询未完成' in result['cache_warning']
    assert result['retrieved_at'] == row.retrieved_at.isoformat()


def test_cache_only_reads_expired_without_network_and_miss_is_explicit():
    cache_article(expired=True)
    transport = Mock()
    assert search_wikipedia('红黑树', cache_only=True, transport=transport)['cache_status'] == 'STALE'
    result = search_wikipedia('布隆过滤器', cache_only=True, transport=transport)
    assert not result['success'] and result['error_code'] == 'WIKIPEDIA_CACHE_MISS'
    transport.get.assert_not_called()


def test_cooldown_suppresses_repeat_and_real_retry_recovers():
    from apps.agents.models import ServiceAvailability
    failed = search_wikipedia('红黑树', transport=transport_for(requests.ConnectionError(), requests.ConnectionError()))
    assert not failed['success'] and ServiceAvailabilityManager('wikipedia').snapshot()['status'] == 'DEGRADED'
    transport = Mock()
    cooldown = search_wikipedia('布隆过滤器', force_refresh=True, transport=transport)
    assert cooldown['error_code'] == 'WIKIPEDIA_TEMPORARILY_UNAVAILABLE'
    transport.get.assert_not_called()
    ServiceAvailability.objects.filter(service='wikipedia').update(next_retry_at=timezone.now() - timedelta(seconds=1))
    recovered = search_wikipedia('红黑树', transport=transport_for(search_response('红黑树'), article_response()))
    assert recovered['success'] and not recovered['from_cache']
    assert ServiceAvailabilityManager('wikipedia').snapshot()['status'] == 'AVAILABLE'


def test_disabled_wikipedia_keeps_cache_and_never_requests(settings):
    settings.WIKIPEDIA_ENABLED = False
    cache_article(expired=True)
    transport = Mock()
    result = search_wikipedia('红黑树', transport=transport)
    assert result['success'] and result['cache_status'] == 'STALE'
    assert not search_wikipedia('哈希表', transport=transport)['success']
    transport.get.assert_not_called()


def test_valid_empty_search_records_reachable_service_without_fabrication():
    result = search_wikipedia('红黑树', transport=transport_for(search_response(), search_response()))
    assert not result['success'] and not result['summary']
    assert ServiceAvailabilityManager('wikipedia').snapshot()['status'] == 'AVAILABLE'


def test_tampered_public_cache_is_not_used():
    row = cache_article()
    WikipediaCache.objects.filter(pk=row.pk).update(summary='篡改摘要')
    assert search_wikipedia('红黑树', cache_only=True)['error_code'] == 'WIKIPEDIA_CACHE_MISS'


@pytest.mark.parametrize('value', ['', 'x' * 121, '我的成绩是多少', 'sk-private-secret', 'student@example.com', 'https://evil.example', '我的密码secret', '学号123456'])
def test_private_or_invalid_query_rejected_without_network(value):
    transport = Mock()
    with pytest.raises(ValidationError):
        search_wikipedia(value, transport=transport)
    assert not WikipediaCache.objects.exists()
    transport.get.assert_not_called()


def test_personal_question_extracts_only_public_concept_for_http_and_shared_cache():
    question = '我是学生张三，学号123456，我想通过维基百科复习红黑树'
    transport = transport_for(search_response('红黑树'), article_response())
    result = search_wikipedia(question, transport=transport)
    assert result['query'] == '红黑树' and extract_public_concept(question) == '红黑树'
    row = WikipediaCache.objects.get()
    assert all('张三' not in str(value) and '123456' not in str(value) for value in row.__dict__.values())
    assert transport.get.call_args_list[0].kwargs['params']['srsearch'] == '红黑树'
    assert normalize_query('什么是 Van Emde Boas tree？') == 'Van Emde Boas tree'


@pytest.mark.parametrize('url', [
    'http://zh.wikipedia.org/wiki/红黑树',
    'https://evil.example/wiki/红黑树',
    'https://zh.wikipedia.org@evil.example/wiki/红黑树',
    'https://en.wikipedia.org/wiki/红黑树',
    'https://zh.wikipedia.org/w/api.php',
    'https://zh.wikipedia.org:invalid/wiki/Foo',
    'https://zh.wikipedia.org:99999/wiki/Foo',
    'https://zh.wikipedia.org/wiki/Foo?redirect=https://evil.example',
    'https://zh.wikipedia.org/wiki/Foo#javascript:alert(1)',
    'https://zh.wikipedia.org/wiki/Foo\n',
    'https://zh.wikipedia.org/wiki/\\evil.example',
])
def test_untrusted_source_url_rejected(url):
    transport = transport_for(search_response('红黑树'), article_response(canonicalurl=url))
    with pytest.raises(ExternalServiceError) as exc:
        MediaWikiClient(transport).search('红黑树', 'zh')
    assert exc.value.code == 'INVALID_EXTERNAL_RESPONSE'


def test_malformed_port_maps_to_service_result_instead_of_escaping_value_error():
    transport = transport_for(search_response('Red-black tree'), article_response('Red-black tree', canonicalurl='https://en.wikipedia.org:invalid/wiki/Red-black_tree'))
    result = search_wikipedia('红黑树', language='en', transport=transport)
    assert not result['success'] and result['error_code'] == 'INVALID_EXTERNAL_RESPONSE'
    assert not result['source_url'] and not WikipediaCache.objects.exists()


@pytest.mark.parametrize('reply,code', [(response({}, 503), 'EXTERNAL_KNOWLEDGE_UNAVAILABLE'), (response(['bad']), 'INVALID_EXTERNAL_RESPONSE'), (response({'error': {'code': 'maxlag'}}), 'INVALID_EXTERNAL_RESPONSE'), (response({'query': {'search': {}}}), 'INVALID_EXTERNAL_RESPONSE'), (requests.Timeout(), 'EXTERNAL_KNOWLEDGE_TIMEOUT'), (requests.ConnectionError(), 'EXTERNAL_KNOWLEDGE_NETWORK_ERROR')])
def test_api_failures_have_explicit_result_without_fake_summary(reply, code):
    result = search_wikipedia('红黑树', language='en', transport=transport_for(reply))
    assert not result['success'] and result['error_code'] == code and result['summary'] == ''
    assert not WikipediaCache.objects.exists()


def test_invalid_json_is_reported():
    broken = response(None)
    broken.iter_content.return_value = [b'not json']
    result = search_wikipedia('红黑树', language='en', transport=transport_for(broken))
    assert result['error_code'] == 'INVALID_EXTERNAL_RESPONSE'


def test_oversized_stream_without_content_length_is_bounded_and_closed():
    oversized = response(None)
    oversized.iter_content.return_value = [b'x' * 500_001, b'x' * 500_001]
    result = search_wikipedia('红黑树', language='en', transport=transport_for(oversized))
    assert result['error_code'] == 'INVALID_EXTERNAL_RESPONSE'
    oversized.close.assert_called_once()


def test_public_query_alias_survives_canonical_title_change_without_private_text():
    transport = transport_for(search_response('Scapegoat tree'), article_response('Scapegoat tree (data structure)', canonicalurl='https://en.wikipedia.org/wiki/Scapegoat_tree', pageid=9))
    first = search_wikipedia('Scapegoat tree', language='en', transport=transport)
    assert first['success']
    row = WikipediaCache.objects.get()
    assert row.query == row.title == 'Scapegoat tree (data structure)'
    assert row.public_aliases['scapegoattree'] is True
    transport = Mock()
    second = search_wikipedia('Scapegoat tree', language='en', transport=transport)
    assert second['from_cache'] and second['title'] == first['title']
    transport.get.assert_not_called()


def test_default_and_fallback_language_follow_settings(settings):
    settings.WIKIPEDIA_DEFAULT_LANGUAGE = 'en'
    transport = transport_for(search_response('Red–black tree'), article_response('Red–black tree', canonicalurl='https://en.wikipedia.org/wiki/Red%E2%80%93black_tree'))
    assert search_wikipedia('红黑树', transport=transport)['language'] == 'en'
    assert transport.get.call_args_list[0].args[0] == 'https://en.wikipedia.org/w/api.php'


def test_disabled_fallback_does_not_return_stale_after_failed_live_query(settings):
    settings.OFFLINE_FALLBACK_ENABLED = False
    cache_article(expired=True)
    result = search_wikipedia('红黑树', transport=transport_for(requests.Timeout(), requests.Timeout()))
    assert not result['success'] and not result['from_cache']
    assert search_wikipedia('红黑树', cache_only=True)['from_cache']


def test_cache_ttl_uses_single_setting(settings):
    settings.WIKIPEDIA_CACHE_TTL_DAYS = 2
    search_wikipedia('红黑树', transport=transport_for(search_response('红黑树'), article_response()))
    row = WikipediaCache.objects.get()
    assert (row.expires_at - row.retrieved_at).days == 2


def test_warmup_single_and_batch_skips_cache_and_reports_counts(monkeypatch):
    monkeypatch.setattr('apps.knowledge.management.commands.warmup_wikipedia.time.sleep', lambda seconds: None)
    cache_article()
    search = Mock(side_effect=[{'success': True, 'from_cache': True, 'cache_status': 'FRESH', 'title': '红黑树'}, {'success': True, 'from_cache': False, 'language': 'zh', 'title': '哈希表', 'page_id': 9}])
    monkeypatch.setattr('apps.knowledge.management.commands.warmup_wikipedia.search_wikipedia', search)
    output = StringIO()
    call_command('warmup_wikipedia', query=['红黑树'], keywords=['哈希表'], stdout=output)
    assert '成功 1；失败 0；跳过有效缓存 1' in output.getvalue()
    assert search.call_count == 2
