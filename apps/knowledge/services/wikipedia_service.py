"""Official MediaWiki search with public, persistent, explicitly dated article caches.

HTTP always targets the two fixed Action API endpoints. The shared cache contains
only API article titles and public extracts, never an original student message.
"""
from dataclasses import asdict, dataclass
from datetime import timedelta
from difflib import SequenceMatcher
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import re
import unicodedata
from urllib.parse import urlencode, urlsplit

import requests
from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from apps.knowledge.models import WikipediaCache
from core.exceptions import ExternalServiceError, ValidationError
from core.services.availability import ServiceAvailabilityManager


API_ENDPOINTS = {language: f'https://{language}.wikipedia.org/w/api.php' for language in ('zh', 'en')}
LICENSE_URL = 'https://creativecommons.org/licenses/by-sa/4.0/'


@dataclass(frozen=True)
class WikipediaResult:
    success: bool
    query: str
    title: str = ''
    page_id: int | None = None
    language: str = 'zh'
    summary: str = ''
    source_url: str = ''
    source_type: str = 'wikipedia'
    retrieved_at: str | None = None
    revision_id: int | None = None
    from_cache: bool = False
    cache_status: str = 'MISS'
    error: str | None = None
    error_code: str | None = None
    query_status: str = 'NOT_FOUND'
    cache_warning: str = ''

    def to_dict(self):
        result = asdict(self)
        source = 'English Wikipedia' if self.language == 'en' else '中文维基百科'
        result.update(
            # Retain the existing external-tool contract for callers and old chats.
            found=self.success, extract=self.summary, source=source + '（外部补充资料）', url=self.source_url,
            license='CC BY-SA 4.0', license_url=LICENSE_URL,
            attribution=f'{source} contributors' if self.success else '',
            revision_url=(API_ENDPOINTS[self.language].replace('/api.php', '/index.php') + '?' +
                          urlencode({'title': self.title, 'oldid': self.revision_id})) if self.revision_id else '',
        )
        return result


@lru_cache(maxsize=1)
def reviewed_keywords():
    path = Path(__file__).resolve().parents[3] / 'knowledge' / 'wikipedia_keywords.json'
    data = json.loads(path.read_text(encoding='utf-8'))
    return tuple(data['keywords'])


def normalized_title(value: str) -> str:
    value = unicodedata.normalize('NFKC', value).casefold()
    return re.sub(r'[\W_]+', '', value, flags=re.UNICODE)


def concept_aliases(query: str) -> list[str]:
    normalized = normalized_title(query)
    for item in reviewed_keywords():
        values = [item['query'], item['en'], *item.get('aliases', [])]
        if any(normalized_title(alias) == normalized for alias in values):
            return values
    return [query]


def extract_public_concept(question: str) -> str | None:
    """Extract only a reviewed public concept; never echo personal context."""
    if not isinstance(question, str):
        return None
    text = unicodedata.normalize('NFKC', question).casefold()
    matches = []
    for item in reviewed_keywords():
        for alias in [item['query'], item['en'], *item.get('aliases', [])]:
            alias = unicodedata.normalize('NFKC', alias).casefold()
            if re.fullmatch(r'[a-z]{2,5}', alias):
                matched = bool(re.search(r'(?<![a-z])' + re.escape(alias) + r'(?![a-z])', text))
            else:
                matched = alias in text
            if matched:
                matches.append((len(alias), item['query']))
    return max(matches, default=(0, None))[1]


def normalize_query(query: str) -> str:
    if not isinstance(query, str) or not query.strip() or len(query) > 120:
        raise ValidationError('百科关键词须为 1 至 120 字。')
    public = extract_public_concept(query)
    if public:
        return public
    value = unicodedata.normalize('NFKC', query).strip()
    value = re.sub(r'^(?:(?:请|帮我)?(?:通过|使用|根据)?(?:实时查询|实时搜索|查询|搜索)?(?:中文|英文)?(?:维基百科|Wikipedia)\s*(?:解释|介绍|查询|搜索)?\s*)', '', value, flags=re.I)
    value = re.sub(r'^(?:请|能否|可以)?(?:解释一下|解释|介绍一下|介绍|什么是|查询|搜索)\s*', '', value)
    value = re.sub(r'(?:是什么|的定义|的原理|怎么理解|如何理解)[?？。]*$', '', value).strip(' ?？。')
    # Unknown public terms may be searched, but a personal message cannot become a
    # global cache key or be sent to Wikimedia. Known concepts were extracted above.
    private = r'(?:我|你的|学生|学号|姓名|成绩|聊天|提交记录|API\s*Key|sk-|password|secret|\b(?:my|mine|student|email)\b|@|https?://|\d{6,})'
    if not value or len(value) > 80 or re.search(private, value, re.I) or not re.fullmatch(r'[\w\s\-–—+().\'’]+', value):
        raise ValidationError('请只输入公开算法或数据结构概念，勿包含姓名、学习记录或密钥。', code='PUBLIC_CONCEPT_REQUIRED')
    return re.sub(r'\s+', ' ', value)


def _source_url(value, language: str) -> str:
    if not isinstance(value, str):
        raise ExternalServiceError('百科响应缺少真实来源链接。', code='INVALID_EXTERNAL_RESPONSE')
    try:
        parsed = urlsplit(value)
        # The Action API's canonical article links need neither query arguments
        # nor fragments. Reject parser-normalized controls and decorated links so
        # stored/displayed provenance is the exact public canonical URL.
        allowed = (
            value == value.strip()
            and not any(ord(character) < 32 or ord(character) == 127 for character in value)
            and '\\' not in value
            and parsed.scheme == 'https'
            and parsed.hostname == f'{language}.wikipedia.org'
            and not parsed.username and not parsed.password
            and parsed.port in (None, 443)
            and parsed.path.startswith('/wiki/')
            and not parsed.query and not parsed.fragment
        )
    except ValueError:
        allowed = False
    if not allowed:
        raise ExternalServiceError('百科响应来源链接不在允许范围。', code='INVALID_EXTERNAL_RESPONSE')
    return value


def _positive_int(value):
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else None


def _relevance(title: str, query: str) -> float:
    candidate = normalized_title(title)
    base_title = normalized_title(re.sub(r'\s*[（(][^）)]*[）)]\s*$', '', title))
    aliases = [normalized_title(alias) for alias in concept_aliases(query)]
    if candidate in aliases:
        return 1.0
    if base_title in aliases:
        return 0.9
    if any(alias and len(alias) >= 4 and alias in candidate and len(candidate) <= len(alias) * 1.7 for alias in aliases):
        return 0.8
    # Conservative title similarity rather than accepting the API's first hit.
    return max((SequenceMatcher(None, candidate, alias).ratio() for alias in aliases if len(alias) >= 5), default=0.0)


class MediaWikiClient:
    def __init__(self, transport=None):
        self.transport = transport or requests.Session()

    def _request(self, language: str, params: dict) -> dict:
        response = None
        try:
            response = self.transport.get(
                API_ENDPOINTS[language],
                params={'action': 'query', 'format': 'json', 'formatversion': 2, 'maxlag': 5, **params},
                headers={'User-Agent': getattr(settings, 'WIKIPEDIA_USER_AGENT', 'AlgoMentor/1.1 (https://github.com/Oookla28/AlgoMentor; educational knowledge retrieval)')},
                timeout=getattr(settings, 'WIKIPEDIA_TIMEOUT', (3, 6)), allow_redirects=False, stream=True,
            )
            if response.status_code >= 300:
                raise ExternalServiceError('维基百科接口暂不可用。', code='EXTERNAL_KNOWLEDGE_UNAVAILABLE')
            if int(response.headers.get('Content-Length', 0) or 0) > 1_000_000:
                raise ValueError('oversized response')
            # Content-Length is optional and can be inaccurate; bound the actual
            # decoded stream before parsing rather than buffering an unlimited body.
            content = bytearray()
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    if len(content) + len(chunk) > 1_000_000:
                        raise ValueError('oversized response')
                    content.extend(chunk)
            value = json.loads(content)
            if not isinstance(value, dict) or 'error' in value or not isinstance(value.get('query'), dict):
                raise ValueError('invalid action api response')
            return value['query']
        except requests.Timeout:
            raise ExternalServiceError('百科查询超时。', code='EXTERNAL_KNOWLEDGE_TIMEOUT', status_code=504) from None
        except requests.RequestException:
            raise ExternalServiceError('百科服务网络不可用。', code='EXTERNAL_KNOWLEDGE_NETWORK_ERROR', status_code=503) from None
        except (ValueError, TypeError, AttributeError):
            raise ExternalServiceError('百科服务响应格式无效。', code='INVALID_EXTERNAL_RESPONSE') from None
        finally:
            if response is not None:
                response.close()

    def search(self, query: str, language: str) -> WikipediaResult:
        search = self._request(language, {'list': 'search', 'srsearch': query, 'srnamespace': 0, 'srlimit': 5, 'srprop': ''})
        rows = search.get('search')
        if not isinstance(rows, list):
            raise ExternalServiceError('百科搜索结果格式无效。', code='INVALID_EXTERNAL_RESPONSE')
        ranked = []
        for row in rows[:5]:
            if not isinstance(row, dict) or not isinstance(row.get('title'), str) or not _positive_int(row.get('pageid')) or row.get('ns', 0) != 0:
                continue
            score = _relevance(row['title'], query)
            if score >= 0.74:
                ranked.append((score, row))
        if not ranked:
            return WikipediaResult(False, query, language=language, error='没有找到相关的可靠百科词条。', error_code='WIKIPEDIA_NOT_FOUND')
        ranked.sort(key=lambda row: row[0], reverse=True)
        ids = [row['pageid'] for _, row in ranked[:3]]
        data = self._request(language, {'prop': 'extracts|info|revisions|pageprops', 'pageids': '|'.join(map(str, ids)), 'redirects': 1, 'exintro': 1, 'explaintext': 1, 'exchars': 1200, 'exlimit': 3, 'inprop': 'url', 'rvprop': 'ids|timestamp', 'ppprop': 'disambiguation'})
        pages = data.get('pages')
        if not isinstance(pages, list):
            raise ExternalServiceError('百科词条响应格式无效。', code='INVALID_EXTERNAL_RESPONSE')
        candidates = []
        for page in pages:
            if not isinstance(page, dict) or page.get('missing') or page.get('ns', 0) != 0 or not _positive_int(page.get('pageid')):
                continue
            title, summary = page.get('title'), page.get('extract')
            props = page.get('pageprops', {})
            if not isinstance(title, str) or not isinstance(summary, str) or not summary.strip() or not isinstance(props, dict) or 'disambiguation' in props:
                continue
            score = _relevance(title, query)
            if score < 0.74:
                continue
            source_url = _source_url(page.get('canonicalurl') or page.get('fullurl'), language)
            revisions = page.get('revisions', [])
            revision_id = _positive_int(revisions[0].get('revid')) if isinstance(revisions, list) and revisions and isinstance(revisions[0], dict) else _positive_int(page.get('lastrevid'))
            candidates.append((score, WikipediaResult(True, query, title=title[:255], page_id=page['pageid'], language=language, summary=summary.strip()[:6000], source_url=source_url, retrieved_at=timezone.now().isoformat(), revision_id=revision_id, cache_status='FRESH', query_status='LIVE')))
        if not candidates:
            return WikipediaResult(False, query, language=language, error='相关词条为歧义页、摘要为空或相关性不足。', error_code='WIKIPEDIA_NOT_FOUND')
        return max(candidates, key=lambda candidate: candidate[0])[1]


def _cached(query: str, languages: list[str]):
    aliases = [normalized_title(alias) for alias in concept_aliases(query)]
    rows = []
    for row in WikipediaCache.objects.filter(Q(normalized_query__in=aliases) | Q(public_aliases__has_any_keys=aliases), language__in=languages, cache_version=1):
        try:
            _source_url(row.source_url, row.language)
        except ExternalServiceError:
            continue
        if row.summary and row.content_hash == hashlib.sha256(row.summary.encode('utf-8')).hexdigest():
            rows.append(row)
    for language in languages:
        candidates = [row for row in rows if row.language == language and row.expires_at > timezone.now()]
        if candidates:
            return max(candidates, key=lambda row: row.retrieved_at)
    for language in languages:
        candidates = [row for row in rows if row.language == language]
        if candidates:
            return max(candidates, key=lambda row: row.retrieved_at)
    return None


def _from_cache(row: WikipediaCache, query: str, *, fallback: bool = False, error: str | None = None, error_code: str | None = None):
    _source_url(row.source_url, row.language)
    stale = row.expires_at <= timezone.now()
    WikipediaCache.objects.filter(pk=row.pk).update(last_accessed_at=timezone.now())
    warning = '以下内容为历史缓存，可能不是最新版本。' if stale else ('实时查询未完成，以下内容来自本地缓存。' if fallback else '')
    return WikipediaResult(True, query, title=row.title, page_id=row.page_id, language=row.language, summary=row.summary, source_url=row.source_url, retrieved_at=row.retrieved_at.isoformat(), revision_id=row.revision_id, from_cache=True, cache_status='STALE' if stale else 'FRESH', query_status='STALE_CACHE' if stale else 'CACHE', error=error, error_code=error_code, cache_warning=warning).to_dict()


def _store(result: WikipediaResult, query: str):
    retrieved = timezone.now()
    ttl = max(0, int(getattr(settings, 'WIKIPEDIA_CACHE_TTL_DAYS', 7)))
    existing = WikipediaCache.objects.filter(language=result.language, page_id=result.page_id).first()
    aliases = dict(existing.public_aliases) if existing and isinstance(existing.public_aliases, dict) else {}
    aliases.update({normalized_title(value): True for value in [query, result.query, result.title]})
    aliases = dict(list(aliases.items())[-16:])
    row, _ = WikipediaCache.objects.update_or_create(language=result.language, page_id=result.page_id, defaults={
        'query': result.title, 'normalized_query': normalized_title(result.title), 'title': result.title,
        'public_aliases': aliases,
        'summary': result.summary, 'source_url': result.source_url, 'revision_id': result.revision_id,
        'retrieved_at': retrieved, 'expires_at': retrieved + timedelta(days=ttl), 'last_accessed_at': retrieved,
        'content_hash': hashlib.sha256(result.summary.encode('utf-8')).hexdigest(), 'cache_version': 1,
    })
    return row


def search_wikipedia(query: str, language: str | None = None, force_refresh: bool = False, cache_only: bool = False, *, transport=None) -> dict:
    """Cache-aside lookup; cache-only never performs a network request."""
    query = normalize_query(query)
    language = language or getattr(settings, 'WIKIPEDIA_DEFAULT_LANGUAGE', 'zh')
    if language not in API_ENDPOINTS or not isinstance(force_refresh, bool) or not isinstance(cache_only, bool):
        raise ValidationError('百科语言或缓存选项无效。')
    fallback = getattr(settings, 'WIKIPEDIA_FALLBACK_LANGUAGE', 'en')
    languages = ['zh', 'en'] if language == 'zh' and fallback == 'en' else [language]
    cached = _cached(query, languages)
    if cached and (cache_only or (not force_refresh and cached.expires_at > timezone.now())):
        return _from_cache(cached, query)
    if cache_only:
        return WikipediaResult(False, query, language=language, error='本地尚无这个概念的 Wikipedia 缓存。', error_code='WIKIPEDIA_CACHE_MISS', query_status='UNAVAILABLE').to_dict()
    manager = ServiceAvailabilityManager('wikipedia')
    enabled = getattr(settings, 'WIKIPEDIA_ENABLED', True)
    if not enabled or not manager.begin_attempt():
        if cached and getattr(settings, 'OFFLINE_FALLBACK_ENABLED', True):
            return _from_cache(cached, query, fallback=True, error='Wikipedia 实时服务暂不可用，使用已保存的公开资料。', error_code='WIKIPEDIA_TEMPORARILY_UNAVAILABLE')
        return WikipediaResult(False, query, language=language, error='Wikipedia 实时服务暂不可用，且没有这个概念的本地缓存。', error_code='WIKIPEDIA_TEMPORARILY_UNAVAILABLE', query_status='UNAVAILABLE').to_dict()
    client = MediaWikiClient(transport)
    failure = None
    last_result = None
    for current_language in languages:
        current_query = query
        if current_language == 'en':
            aliases = concept_aliases(query)
            current_query = next((alias for alias in aliases if re.search(r'[a-zA-Z]', alias) and not re.search(r'[\u4e00-\u9fff]', alias)), query)
        try:
            result = client.search(current_query, current_language)
            last_result = result
            if result.success:
                row = _store(result, query)
                manager.record_success()
                output = result.to_dict()
                output.update(query=query, retrieved_at=row.retrieved_at.isoformat())
                return output
        except ExternalServiceError as exc:
            failure = exc
    if last_result is not None:
        # A valid empty search is evidence of reachability, not fabricated content.
        manager.record_success()
    elif failure:
        manager.record_failure(failure.code)
    if cached and getattr(settings, 'OFFLINE_FALLBACK_ENABLED', True):
        return _from_cache(cached, query, fallback=True, error=str(failure) if failure else last_result.error, error_code=failure.code if failure else last_result.error_code)
    if failure:
        return WikipediaResult(False, query, language=language, error=str(failure), error_code=failure.code, query_status='UNAVAILABLE').to_dict()
    return WikipediaResult(False, query, language=language, error=last_result.error if last_result else '没有找到可靠的百科词条。', error_code='WIKIPEDIA_NOT_FOUND').to_dict()
