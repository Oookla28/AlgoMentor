"""Literature library and local related-paper recommendations.

Recommendations only use:
1. the user's own active documents in the selected workspace;
2. the user's own documents in their other private workspaces;
3. a small built-in catalog that is explicitly offline and unverified.

No other user's private documents, shared spaces, or network requests are used.
"""

import json
import math
from pathlib import Path
import re

from django.conf import settings

from apps.knowledge.services.sparse_retrieval import tokenize

from ..models import Workspace, WorkspaceDocument
from ..permissions import ensure_readable
from .documents import ACTIVE_STATUSES

CATALOG_PATH = Path(settings.BASE_DIR) / 'knowledge/literature_catalog.json'
_CATALOG_CACHE = {'mtime': None, 'papers': []}

STOPWORDS = {
    '本文', '我们', '研究', '方法', '实验', '结果', '论文', '文献', '使用', '基于', '一个',
    'the', 'and', 'for', 'with', 'this', 'that', 'are', 'was', 'were', 'from', 'into',
    'using', 'use', 'paper', 'method', 'results', 'experiments',
}


def _catalog():
    if not CATALOG_PATH.is_file():
        return []
    mtime = CATALOG_PATH.stat().st_mtime_ns
    if _CATALOG_CACHE['mtime'] == mtime:
        return _CATALOG_CACHE['papers']
    try:
        payload = json.loads(CATALOG_PATH.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return []
    papers = payload.get('papers') or []
    _CATALOG_CACHE.update({'mtime': mtime, 'papers': papers})
    return papers


def _english_terms(text):
    return {
        term.lower() for term in re.findall(r'[A-Za-z][A-Za-z0-9_\-]{2,}', str(text or ''))
    }


def _keywords(text):
    terms = {
        term.lower() for term in tokenize(str(text or ''))
        if len(term) > 1 and term.lower() not in STOPWORDS
    }
    terms |= _english_terms(text)
    return {term for term in terms if term not in STOPWORDS}


def _document_title(document, content=''):
    for line in str(content or '').splitlines():
        stripped = line.strip()
        if stripped.startswith('# '):
            return stripped[2:].strip()[:160]
    return Path(document.name).stem.replace('_', ' ').replace('-', ' ')[:160]


def _document_profile(document):
    chunks = list(
        document.chunks.filter(is_active=True).exclude(chunk_type='parent')
        .order_by('page_number', 'chunk_id').values_list('content', flat=True)[:4]
    )
    content = '\n'.join(chunks)
    title = _document_title(document, content)
    terms = _keywords(f'{title} {content[:2400]}')
    return {
        'document_id': document.pk,
        'name': document.name,
        'title': title,
        'page_count': document.page_count,
        'terms': terms,
    }


def _display_reasons(shared, raw_keywords=(), limit=4):
    """Prefer human-readable catalog keywords over raw character bigrams."""
    reasons = []
    for keyword in raw_keywords:
        text = str(keyword or '').strip()
        if not text:
            continue
        if _keywords(text) & shared and text not in reasons:
            reasons.append(text)
        if len(reasons) >= limit:
            return reasons
    for term in sorted(shared, key=lambda value: (-len(value), value)):
        if re.search(r'[\u4e00-\u9fff]', term) or len(term) < 3:
            continue
        if term not in reasons:
            reasons.append(term)
        if len(reasons) >= limit:
            break
    return reasons or ['主题相近']


def _score(shared, source_terms, target_terms, title_shared=0):
    if not shared:
        return 0.0
    return round((len(shared) * 2 + title_shared * 3) / math.sqrt(max(1, len(source_terms)) * max(1, len(target_terms))), 4)


def recommend_for_workspace(user, workspace, limit=6):
    ensure_readable(user, workspace)
    links = list(
        WorkspaceDocument.objects.filter(workspace=workspace, status__in=ACTIVE_STATUSES)
        .select_related('document').order_by('created_at')
    )
    documents = [link.document for link in links if link.document_id]
    profiles = [_document_profile(document) for document in documents]
    if not profiles:
        return {
            'documents': [], 'recommendations': [],
            'message': '这个空间还没有可检索文献；先上传论文，再生成相关推荐。',
        }
    source_terms = set().union(*(profile['terms'] for profile in profiles))
    source_titles = ' '.join(profile['title'] for profile in profiles).lower()
    recommendations = []
    known_titles = {profile['title'].lower() for profile in profiles}
    for paper in _catalog():
        title = str(paper.get('title') or '')
        if title.lower() in known_titles or title.lower()[:40] in source_titles:
            continue
        target_terms = _keywords(f"{title} {paper.get('keywords') or ''} {paper.get('summary') or ''}")
        shared = source_terms & target_terms
        if not shared:
            continue
        recommendations.append({
            'source': 'catalog',
            'title': title,
            'authors': paper.get('authors') or '',
            'year': paper.get('year'),
            'venue': paper.get('venue') or '',
            'url': paper.get('url') or '',
            'summary': paper.get('summary') or '',
            'reason_terms': _display_reasons(shared, paper.get('keywords') or []),
            'score': _score(shared, source_terms, target_terms),
            'note': '内置离线目录，未联网抓取；引用前请核对原文。',
        })

    # Other private workspaces owned by the same user; never another account's space.
    current_ids = {profile['document_id'] for profile in profiles}
    other_links = (
        WorkspaceDocument.objects.filter(
            workspace__owner=user, workspace__visibility='private',
            status__in=ACTIVE_STATUSES,
        )
        .exclude(workspace=workspace)
        .exclude(document_id__in=current_ids)
        .select_related('document', 'workspace')
        .order_by('-created_at')[:40]
    )
    for link in other_links:
        if link.document_id is None:
            continue
        profile = _document_profile(link.document)
        shared = source_terms & profile['terms']
        if not shared:
            continue
        recommendations.append({
            'source': 'user_library',
            'title': profile['title'],
            'authors': '我的文献库',
            'year': None,
            'venue': link.workspace.name,
            'url': f'/workbench/?view=overview&workspace={link.workspace_id}',
            'summary': '来自你自己的另一个私有空间，仅你可见。',
            'reason_terms': _display_reasons(shared),
            'score': _score(shared, source_terms, profile['terms']),
            'workspace_id': link.workspace_id,
            'document_id': link.document_id,
            'note': '同一账号的私有文献；不会跨用户推荐。',
        })
    recommendations.sort(key=lambda row: (-row['score'], row['title']))
    return {
        'documents': [
            {
                'document_id': profile['document_id'], 'name': profile['name'],
                'title': profile['title'], 'page_count': profile['page_count'],
            }
            for profile in profiles
        ],
        'recommendations': recommendations[:max(1, min(int(limit or 6), 12))],
        'message': '' if recommendations else '暂未找到关键词重叠的相关文献；可继续上传同主题论文。',
        'catalog_note': '内置目录为离线示例，未联网抓取。',
    }
