"""Offline evaluation for legacy vs EvidenceRAG advanced retrieval.

Reads tests/evaluation/rag_cases.json, runs both retrieval modes against the
locally indexed database, and writes tests/evaluation/evidence_rag_results.json.
No LLM, Wikipedia or external network call is made. If no advanced index exists,
advanced metrics are reported as SKIPPED rather than fabricated.
"""

import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')


def _hit(citations, case):
    expected = (case.get('expected_text') or '').strip()
    pages = case.get('expected_pages') or []
    if not expected:
        return False
    for citation in citations:
        content = (getattr(citation, 'content', '') or '') + '\n' + (getattr(citation, 'context', '') or '')
        if expected in content and (not pages or citation.page_number in pages):
            return True
    return False


def _citations(result):
    return result if isinstance(result, list) else getattr(result, 'citations', [])


def main():
    import django
    django.setup()
    from apps.knowledge.services.retrieval_service import retrieve_knowledge, retrieve_knowledge_with_trace

    cases = json.loads((ROOT / 'tests/evaluation/rag_cases.json').read_text(encoding='utf-8'))
    rows = []
    legacy_hits = advanced_hits = covered = outside = legacy_refusals = advanced_refusals = 0
    advanced_available = True
    for case in cases:
        query = case['query']
        is_covered = bool(case.get('covered'))
        covered += 1 if is_covered else 0
        outside += 0 if is_covered else 1
        started = time.monotonic()
        try:
            legacy = retrieve_knowledge(query)
            legacy_error = ''
        except Exception as exc:
            legacy = []
            legacy_error = getattr(exc, 'code', type(exc).__name__)
        legacy_latency = int((time.monotonic() - started) * 1000)
        legacy_row = {
            'mode': 'legacy', 'ids': [citation.chunk_id for citation in legacy],
            'hit': _hit(legacy, case), 'latency_ms': legacy_latency, 'error': legacy_error,
        }
        if is_covered and legacy_row['hit']:
            legacy_hits += 1
        if not is_covered and not legacy:
            legacy_refusals += 1

        started = time.monotonic()
        advanced = retrieve_knowledge_with_trace(query, mode='advanced')
        advanced_latency = int((time.monotonic() - started) * 1000)
        advanced_citations = _citations(advanced)
        if getattr(advanced, 'mode', '') != 'advanced':
            advanced_available = False
        advanced_row = {
            'mode': 'advanced',
            'ids': [citation.chunk_id for citation in advanced_citations],
            'hit': _hit(advanced_citations, case),
            'latency_ms': advanced_latency,
            'evidence_sufficient': bool(getattr(advanced, 'evidence_sufficient', False)),
            'fallback': getattr(advanced, 'fallback', {}),
            'trace_id': getattr(advanced, 'trace_id', ''),
            'trace_rows': len(getattr(advanced, 'retrieval_trace', []) or []),
            'conflicts': len(getattr(advanced, 'conflicts', []) or []),
            'query_variants': getattr(advanced, 'query_variants', []),
        }
        if is_covered and advanced_row['hit']:
            advanced_hits += 1
        if not is_covered and not advanced_citations:
            advanced_refusals += 1
        rows.append({'id': case['id'], 'query': query, 'covered': is_covered, 'legacy': legacy_row, 'advanced': advanced_row})

    result = {
        'status': 'PASSED' if advanced_available and advanced_hits == covered and advanced_refusals == outside else ('SKIPPED_NO_ADVANCED_INDEX' if not advanced_available else 'FAILED'),
        'advanced_available': advanced_available,
        'cases': len(cases),
        'covered_cases': covered,
        'outside_cases': outside,
        'legacy_hit': legacy_hits,
        'advanced_hit': advanced_hits,
        'legacy_refusals': legacy_refusals,
        'advanced_refusals': advanced_refusals,
        'notes': 'Small local evaluation only; not a production accuracy claim. Advanced mode uses the configured embedding/index.',
        'rows': rows,
    }
    output = ROOT / 'tests/evaluation/evidence_rag_results.json'
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({key: result[key] for key in ('status', 'advanced_available', 'cases', 'legacy_hit', 'advanced_hit', 'legacy_refusals', 'advanced_refusals')}, ensure_ascii=False))
    raise SystemExit(0 if result['status'] in ('PASSED', 'SKIPPED_NO_ADVANCED_INDEX') else 1)


if __name__ == '__main__':
    main()
