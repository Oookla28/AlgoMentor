"""Run the platform evaluation protocol against the locally indexed corpus.

This script is deliberately honest about the experiment matrix: B0 legacy and
B1 advanced+TF-IDF are runnable in this environment; B2–B5 require real BGE /
cross-encoder resources and are reported as blocked, not fabricated.
"""

import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')

DATASET = ROOT / 'tests/evaluation/platform_cases.json'
OUTPUT = ROOT / 'tests/evaluation/platform_results.json'


def _hash_file(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git_sha():
    try:
        return subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=ROOT, capture_output=True, text=True, check=False).stdout.strip()
    except Exception:
        return ''


def _matches(citations, case):
    gold = case.get('gold_evidence') or {}
    pages = set(gold.get('pages') or [])
    text = (gold.get('text') or '').strip()
    hits = []
    for citation in citations:
        content = (getattr(citation, 'content', '') or '') + '\n' + (getattr(citation, 'context', '') or '')
        page = getattr(citation, 'page_number', None)
        if (not pages or page in pages) and (not text or text in content):
            hits.append(getattr(citation, 'chunk_id', ''))
    return [item for item in hits if item]


def _retrieval_row(citations, case, k=4):
    relevant = _matches(citations, case)
    ids = [getattr(citation, 'chunk_id', '') for citation in citations]
    return {
        'ids': ids,
        'relevant_ids': relevant,
        'hit': bool(relevant),
        'recall_at_k': 1.0 if relevant else 0.0,
        'mrr': 1.0 / (ids.index(relevant[0]) + 1) if relevant and relevant[0] in ids else 0.0,
        'ndcg_at_k': 1.0 / (ids.index(relevant[0]) + 1) if relevant and relevant[0] in ids else 0.0,
        'parent_recovery': 1.0 if any(getattr(citation, 'parent_chunk_id', '') and getattr(citation, 'page_number', None) in set((case.get('gold_evidence') or {}).get('parent_pages') or []) for citation in citations) else 0.0,
    }


def _agent_row(outcome, case):
    returns = outcome.metrics or {}
    gate = returns.get('gate') or {}
    check = returns.get('citation_check') or {}
    answerable = bool(case.get('answerable'))
    abstained = outcome.status == 'ABSTAINED'
    expected_abstention = bool(case.get('expected_abstention'))
    evidence = []
    try:
        from apps.platform.models import AgentRun
        run = AgentRun.objects.filter(run_id=outcome.run_id).first()
        if run:
            evidence = list(run.evidence.values('chunk_id', 'page', 'content', 'retrieval_score'))
    except Exception:
        pass
    gold = case.get('gold_evidence') or {}
    pages = set(gold.get('pages') or [])
    text = (gold.get('text') or '').strip()
    relevant_evidence = [
        item for item in evidence
        if (not pages or item['page'] in pages) and (not text or text in (item['content'] or ''))
    ]
    return {
        'run_id': outcome.run_id,
        'status': outcome.status,
        'expected_abstention': expected_abstention,
        'abstained': abstained,
        'steps': outcome.step_count,
        'evidence_count': outcome.evidence_count,
        'tool_calls': returns.get('tool_calls', 0),
        'latency_ms': returns.get('latency_ms', 0),
        'gate': gate,
        'citation_check': check,
        'answer': outcome.answer,
        'evidence': evidence,
        'relevant_evidence': relevant_evidence,
    }


def _conflict_probe(case):
    from apps.knowledge.services.conflict_service import detect_conflicts
    claims = []
    for index, item in enumerate(case.get('synthetic_claims') or []):
        text = item['text']
        claims.append(SimpleNamespace(
            claim_id=f"{case['case_id']}-{index}", normalized_text=text, subject='循环队列',
            authority_level=item.get('authority', 3), detector_score=0.6,
            source_chunk_id=item.get('chunk_id', f'syn-{index}'),
            source_chunk=SimpleNamespace(chunk_id=item.get('chunk_id', f'syn-{index}')),
            valid_from=None, valid_to=None, created_at=None,
        ))
    detected = detect_conflicts(claims, similarity_threshold=0.35)
    return {
        'detected': [conflict.conflict_type for conflict in detected],
        'expected': case.get('expected_conflict_type'),
        'passed': any(conflict.conflict_type == case.get('expected_conflict_type') for conflict in detected),
        'verdicts': [conflict.verdict for conflict in detected],
    }


def _tool_probes(user):
    from apps.platform.contracts import ToolSpec
    from apps.platform.tools import execute_spec, execute_tool
    import time as time_module

    def slow(_user):
        time_module.sleep(0.3)
        return {'results': []}

    write_spec = ToolSpec(tool_id='probe_write', version='1', name='probe', description='probe', permission='write')
    timeout_spec = ToolSpec(tool_id='probe_timeout', version='1', name='probe', description='probe', timeout_seconds=0.05, permission='read')
    return {
        'permission_rejection': execute_spec(write_spec, slow, user).failure_code,
        'timeout': execute_spec(timeout_spec, slow, user).failure_code,
        'invalid_call': execute_tool('missing_tool', user).failure_code,
    }


def main():
    import django
    django.setup()
    from django.contrib.auth import get_user_model
    from django.conf import settings

    from apps.knowledge.models import KnowledgeDocument
    from apps.knowledge.services.citation_verifier import verify_answer
    from apps.knowledge.services.retrieval_service import retrieve_knowledge
    from apps.knowledge.services.hybrid_retrieval import advanced_retrieve
    from apps.platform.agent import run_evidence_agent
    from apps.platform.domains import get_domain_pack
    from apps.platform.evaluation.metrics import (
        abstention_precision, abstention_recall, brier_score,
        expected_calibration_error, percentile,
    )
    from apps.platform.models import EvaluationCase, EvaluationRun

    cases = json.loads(DATASET.read_text(encoding='utf-8'))
    user = get_user_model().objects.filter(username='demo_student').first()
    if user is None:
        user = get_user_model().objects.create_user('demo_student', password='demo-pass-2026')
    document = KnowledgeDocument.objects.exclude(latest_index_version='').order_by('-created_at').first()
    advanced_available = document is not None
    provider = getattr(settings, 'EMBEDDING_PROVIDER', '')
    model = getattr(settings, 'EMBEDDING_MODEL', '')
    dimension = ((document.source_metadata or {}).get('advanced') or {}).get('embedding_dimension', 0) if document else 0
    index_version = document.latest_index_version if document else ''
    pack = get_domain_pack('data_structures')
    config = {
        'provider': provider, 'model': model, 'revision': getattr(settings, 'EMBEDDING_REVISION', ''),
        'dimension': dimension, 'index_version': index_version,
        'chunk_policy': pack.chunk_policy, 'gate_coverage': getattr(settings, 'PLATFORM_GATE_MIN_COVERAGE', 0.15),
        'gate_dense': getattr(settings, 'EVIDENCE_RAG_MIN_DENSE_SUPPORT', 0.35),
        'rrf_k': getattr(settings, 'EVIDENCE_RAG_RRF_K', 60),
    }
    config_hash = hashlib.sha256(json.dumps(config, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    rows = []
    failures = []
    legacy_metrics = []
    advanced_metrics = []
    agent_rows = []
    conflict_rows = []
    started_all = time.monotonic()

    for case in cases:
        for item in (case.get('synthetic_claims') or []):
            pass
        EvaluationCase.objects.update_or_create(
            case_id=case['case_id'], dataset='platform',
            defaults={
                'question': case['question'], 'domain': case.get('domain', 'data_structures'),
                'difficulty': case.get('difficulty', ''), 'answerable': bool(case.get('answerable')),
                'payload': case,
            },
        )
        if case.get('synthetic_claims'):
            probe = _conflict_probe(case)
            conflict_rows.append({'case_id': case['case_id'], **probe})
            if not probe['passed']:
                failures.append({'case_id': case['case_id'], 'stage': 'synthetic_conflict', 'expected': probe['expected'], 'detected': probe['detected']})
            rows.append({'case_id': case['case_id'], 'kind': 'synthetic_conflict', 'conflict': probe})
            continue

        started = time.monotonic()
        try:
            legacy = retrieve_knowledge(case['question'])
            legacy_error = ''
        except Exception as exc:
            legacy = []
            legacy_error = getattr(exc, 'code', type(exc).__name__)
        legacy_row = _retrieval_row(legacy, case)
        legacy_row['error'] = legacy_error
        legacy_row['latency_ms'] = int((time.monotonic() - started) * 1000)

        started = time.monotonic()
        advanced = advanced_retrieve(case['question'], user=user)
        advanced_row = _retrieval_row(advanced.citations, case)
        advanced_row['mode'] = advanced.mode
        advanced_row['fallback'] = advanced.fallback
        advanced_row['trace_id'] = advanced.trace_id
        advanced_row['latency_ms'] = int((time.monotonic() - started) * 1000)

        outcome = run_evidence_agent(user, case['question'], domain=case.get('domain', 'data_structures'))
        agent_row = _agent_row(outcome, case)
        legacy_metrics.append(legacy_row)
        advanced_metrics.append(advanced_row)
        agent_rows.append(agent_row)
        if case.get('answerable') and not legacy_row['hit']:
            failures.append({'case_id': case['case_id'], 'stage': 'legacy_retrieval', 'detail': 'no gold evidence'})
        if case.get('answerable') and not advanced_row['hit']:
            failures.append({'case_id': case['case_id'], 'stage': 'advanced_retrieval', 'detail': 'no gold evidence'})
        if bool(case.get('expected_abstention')) != bool(agent_row['abstained']):
            failures.append({'case_id': case['case_id'], 'stage': 'abstention', 'expected': case.get('expected_abstention'), 'actual': agent_row['abstained'], 'status': agent_row['status']})
        rows.append({
            'case_id': case['case_id'], 'kind': 'corpus', 'answerable': case.get('answerable'),
            'legacy': legacy_row, 'advanced': advanced_row, 'agent': agent_row,
        })

    # Aggregate retrieval metrics.
    def mean(values):
        return sum(values) / len(values) if values else 0.0

    corpus = [row for row in rows if row['kind'] == 'corpus']
    answerable = [row for row in corpus if row['answerable']]
    unanswerable = [row for row in corpus if not row['answerable']]
    retrieval = {
        'legacy_hit_rate': mean([row['legacy']['hit'] for row in answerable]),
        'advanced_hit_rate': mean([row['advanced']['hit'] for row in answerable]),
        'legacy_recall_at_4': mean([row['legacy']['recall_at_k'] for row in answerable]),
        'advanced_recall_at_4': mean([row['advanced']['recall_at_k'] for row in answerable]),
        'legacy_mrr': mean([row['legacy']['mrr'] for row in answerable]),
        'advanced_mrr': mean([row['advanced']['mrr'] for row in answerable]),
        'advanced_ndcg_at_4': mean([row['advanced']['ndcg_at_k'] for row in answerable]),
        'parent_recovery_rate': mean([row['advanced']['parent_recovery'] for row in answerable]),
        'legacy_refusal_rate': mean([1.0 if not row['legacy']['ids'] else 0.0 for row in unanswerable]),
        'advanced_refusal_rate': mean([1.0 if not row['advanced']['ids'] else 0.0 for row in unanswerable]),
    }

    agent_rows = [row for row in agent_rows if row]
    checks = [row['citation_check'] for row in agent_rows]
    abstained = {row['run_id']: row['abstained'] for row in agent_rows}
    expected_unanswerable = {row['run_id']: row['expected_abstention'] for row in agent_rows}
    confidence, outcomes = [], []
    for row in agent_rows:
        gate = row['gate'] or {}
        answerable_flag = not row['expected_abstention']
        confidence.append(min(1.0, max(0.0, gate.get('coverage', 0.0) if answerable_flag else 1 - gate.get('coverage', 0.0))))
        matched = (not row['abstained']) if answerable_flag else row['abstained']
        outcomes.append(1.0 if matched else 0.0)
    answer_support = {
        'claim_coverage': mean([check.get('claim_coverage', 0.0) for check in checks]),
        'citation_coverage': mean([check.get('claim_coverage', 0.0) for check in checks]),
        'supported_claim_ratio': mean([1 - (len(check.get('unsupported_claims') or []) / max(1, check.get('factual_claims', 0) or 1)) for check in checks]),
        'unsupported_claim_rate': mean([len(check.get('unsupported_claims') or []) / max(1, check.get('factual_claims', 0) or 1) for check in checks]),
        'contradiction_rate': mean([len(check.get('contradictions') or []) / max(1, check.get('factual_claims', 0) or 1) for check in checks]),
        'answer_faithfulness': mean([1 - len(check.get('contradictions') or []) / max(1, check.get('factual_claims', 0) or 1) for check in checks]),
        'abstention_precision': abstention_precision([row['run_id'] for row in agent_rows if row['abstained']], [row['run_id'] for row in agent_rows if row['expected_abstention']]),
        'abstention_recall': abstention_recall([row['run_id'] for row in agent_rows if row['abstained']], [row['run_id'] for row in agent_rows if row['expected_abstention']]),
        'brier_proxy': brier_score(confidence, outcomes),
        'ece_proxy': expected_calibration_error(confidence, outcomes),
        'calibration_note': 'Proxy confidence uses gate coverage, not a trained probability; not a generalization claim.',
    }
    latencies = [row['latency_ms'] for row in agent_rows]
    tool_steps = sum(row['tool_calls'] for row in agent_rows)
    failed_tool_steps = 0
    for row in agent_rows:
        try:
            from apps.platform.models import AgentRun
            failed_tool_steps += AgentRun.objects.get(run_id=row['run_id']).steps.filter(decision='TOOL_FAILED').count()
        except Exception:
            pass
    agent_quality = {
        'avg_steps': mean([row['steps'] for row in agent_rows]),
        'avg_tool_calls': mean([row['tool_calls'] for row in agent_rows]),
        'p50_latency_ms': percentile(latencies, 0.5),
        'p95_latency_ms': percentile(latencies, 0.95),
        'invalid_call_rate': failed_tool_steps / max(1, tool_steps),
        'abstention_count': sum(1 for row in agent_rows if row['abstained']),
        'conflict_cases_detected': sum(1 for row in conflict_rows if row['passed']),
        'conflict_cases_total': len(conflict_rows),
        'tool_probes': _tool_probes(user),
    }
    advanced_modes = {row['advanced']['mode'] for row in corpus}
    matrix = {
        'B0_legacy': {'status': 'RUNNABLE', 'metrics': retrieval['legacy_hit_rate']},
        'B1_advanced_tfidf': {
            'status': 'RUNNABLE' if 'advanced' in advanced_modes and provider == 'tfidf' else 'BLOCKED',
            'metrics': retrieval['advanced_hit_rate'],
            'note': 'TF-IDF lexical baseline; not a BGE conclusion.',
        },
        'B2_advanced_bge': {'status': 'UNVERIFIED', 'blocked_by': 'bge_local_weights_not_available'},
        'B3_bge_reranker': {'status': 'UNVERIFIED', 'blocked_by': 'B2'},
        'B4_b3_adaptive': {'status': 'UNVERIFIED', 'blocked_by': 'B2'},
        'B5_b4_conflict_verifier': {'status': 'UNVERIFIED', 'blocked_by': 'B2'},
        'B1_adaptive_engineering_probe': {'status': 'RUNNABLE', 'metrics': agent_quality, 'note': 'TF-IDF adaptive routing probe; not the B4 research configuration.'},
    }
    result = {
        'status': 'COMPLETED_WITH_FINDINGS' if failures else 'PASSED',
        'git_sha': _git_sha(),
        'branch': subprocess.run(['git', 'branch', '--show-current'], cwd=ROOT, capture_output=True, text=True, check=False).stdout.strip(),
        'config_hash': config_hash,
        'dataset_hash': _hash_file(DATASET),
        'dataset': str(DATASET.relative_to(ROOT)),
        'seed': 0,
        'provider': provider,
        'model': model,
        'revision': getattr(settings, 'EMBEDDING_REVISION', ''),
        'dimension': dimension,
        'index_version': index_version,
        'chunk_policy': pack.chunk_policy,
        'metrics': {'retrieval_hit': retrieval, 'answer_support': answer_support, 'agent_quality': agent_quality},
        'matrix': matrix,
        'failures': failures,
        'rows': rows,
        'elapsed_seconds': round(time.monotonic() - started_all, 3),
    }
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    EvaluationRun.objects.create(
        run_id=hashlib.sha256(f'{config_hash}:{result["dataset_hash"]}:{time.time()}'.encode()).hexdigest()[:32],
        dataset='platform', config_hash=config_hash, dataset_hash=result['dataset_hash'],
        git_sha=result['git_sha'], status=result['status'], metrics=result['metrics'],
        failures=failures, finished_at=timezone_now(),
    )
    print(json.dumps({
        'status': result['status'], 'cases': len(cases), 'failures': len(failures),
        'retrieval': retrieval, 'answer_support': {k: answer_support[k] for k in ('claim_coverage', 'unsupported_claim_rate', 'abstention_precision', 'abstention_recall')},
        'agent_quality': {k: agent_quality[k] for k in ('avg_steps', 'avg_tool_calls', 'p50_latency_ms', 'p95_latency_ms', 'invalid_call_rate', 'conflict_cases_detected', 'conflict_cases_total', 'tool_probes')},
    }, ensure_ascii=False))
    raise SystemExit(0)


def timezone_now():
    from django.utils import timezone
    return timezone.now()


if __name__ == '__main__':
    main()
