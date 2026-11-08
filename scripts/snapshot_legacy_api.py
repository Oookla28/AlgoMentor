"""Capture legacy knowledge API/schema golden snapshots without external services."""

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')


def main():
    import django
    django.setup()
    from dataclasses import fields
    from django.contrib.auth import get_user_model
    from django.test import Client
    from apps.knowledge.services.retrieval_service import Citation

    user = get_user_model().objects.filter(username='demo_student').first()
    if user is None:
        user = get_user_model().objects.create_user('demo_student', password='demo-pass-2026')
    client = Client()
    client.force_login(user)

    def request(path):
        response = client.get(path)
        try:
            payload = response.json()
        except ValueError:
            payload = {'raw_prefix': response.content[:200].decode('utf-8', 'replace')}
        return {'status': response.status_code, 'payload': payload}

    hit = request('/api/v1/knowledge/search/?q=%E5%BE%AA%E7%8E%AF%E9%98%9F%E5%88%97%E5%88%A4%E6%BB%A1%E6%9D%A1%E4%BB%B6')
    miss = request('/api/v1/knowledge/search/?q=%E9%87%8F%E5%AD%90%E5%BC%95%E5%8A%9B%E9%BB%91%E6%B4%9E%E9%9C%8D%E9%87%91%E8%BE%90%E5%B0%84')
    empty = request('/api/v1/knowledge/search/?q=')
    client.logout()
    anonymous = request('/api/v1/knowledge/search/?q=KMP')
    client.force_login(user)

    page_smoke = {}
    for path in ('/', '/knowledge/', '/knowledge/local/', '/knowledge/wikipedia/', '/tutor/', '/graph/', '/visualizations/', '/problems/', '/learning/', '/mistakes/', '/reports/'):
        response = client.get(path)
        page_smoke[path] = response.status_code

    citation_keys = [field.name for field in fields(Citation)]
    hit_data = hit['payload'].get('data', {})
    first = (hit_data.get('citations') or [{}])[0]
    snapshot = {
        'note': 'Schema/contract snapshot for the legacy knowledge search API. Generated on the local TF-IDF index; scores can vary by index.',
        'environment': {
            'embedding_provider': os.environ.get('EMBEDDING_PROVIDER', 'setting-default'),
            'chroma_path': os.environ.get('CHROMA_PATH', 'setting-default'),
            'rag_min_score': os.environ.get('RAG_MIN_SCORE', 'setting-default'),
        },
        'citation_dataclass_fields': citation_keys,
        'search_response_top_level_keys': sorted((hit['payload'].get('data') or {}).keys()),
        'citation_keys': sorted(first.keys()) if first else [],
        'hit': hit,
        'miss': miss,
        'empty_query': empty,
        'anonymous': anonymous,
        'page_smoke': page_smoke,
    }
    output = ROOT / 'docs/evidence_rag/golden/legacy_api_snapshot.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({
        'output': str(output.relative_to(ROOT)),
        'hit_status': hit['status'],
        'hit_count': len(hit_data.get('citations') or []),
        'miss_status': miss['status'],
        'miss_count': len((miss['payload'].get('data') or {}).get('citations') or []),
        'empty_status': empty['status'],
        'anonymous_status': anonymous['status'],
        'pages_non_200': {k: v for k, v in page_smoke.items() if v != 200},
    }, ensure_ascii=False))


if __name__ == '__main__':
    main()
