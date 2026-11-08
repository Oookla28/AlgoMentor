"""Run the real workbench development set and save raw per-case results.

Requires a seeded demo account (see ``seed_workbench_demo``). The command does
not synthesize scores: every metric is computed from the runs it actually made.
"""

from datetime import datetime, timezone as dt_timezone
import hashlib
import json
import os
from pathlib import Path
import statistics
import subprocess

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from apps.platform.models import AgentRun
from apps.workspace.evaluation.cases import CASES
from apps.workspace.models import Workspace
from apps.workspace.services.executor import execute_run
from apps.workspace.services.tasks import claim_next, create_task


def _git_sha():
    env_sha = os.getenv('ALGOMENTOR_GIT_SHA', '').strip()
    if env_sha:
        return env_sha
    try:
        result = subprocess.run(
            ['git', 'rev-parse', 'HEAD'], cwd=settings.BASE_DIR,
            capture_output=True, text=True, timeout=5, check=False,
        )
        return result.stdout.strip() if result.returncode == 0 else ''
    except Exception:
        return ''


def _config_hash():
    payload = {
        'embedding_provider': getattr(settings, 'EMBEDDING_PROVIDER', ''),
        'embedding_model': getattr(settings, 'EMBEDDING_MODEL', ''),
        'embedding_revision': getattr(settings, 'EMBEDDING_REVISION', ''),
        'rerank_backend': getattr(settings, 'EVIDENCE_RAG_RERANK_BACKEND', ''),
        'gate_coverage': getattr(settings, 'PLATFORM_GATE_MIN_COVERAGE', 0),
        'gate_support': getattr(settings, 'PLATFORM_GATE_MIN_SUPPORT', 0),
        'top_k': getattr(settings, 'EVIDENCE_RAG_TOP_K', 0),
        'index_version': getattr(settings, 'EVIDENCE_RAG_INDEX_VERSION', ''),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode('utf-8')).hexdigest()


def _artifact_text(run):
    return '\n'.join(run.artifacts.values_list('content', flat=True))


def _haystack(run):
    parts = [run.answer_text or '']
    parts.extend(run.evidence.values_list('content', flat=True))
    parts.append(_artifact_text(run))
    return '\n'.join(parts)


def _term_hit(text, term):
    return bool(term) and term.lower() in (text or '').lower()


def _mrr(run, gold_terms):
    for rank, evidence in enumerate(run.evidence.all().order_by('-retrieval_score'), 1):
        if any(_term_hit(evidence.content, term) for term in gold_terms):
            return 1.0 / rank
    return 0.0


def _case_result(case, run):
    haystack = _haystack(run)
    terms = list(case.get('gold_terms') or [])
    recall = sum(1 for term in terms if _term_hit(haystack, term)) / len(terms) if terms else 0.0
    citation_check = (run.metrics or {}).get('citation_check') or {}
    unsupported = len(citation_check.get('unsupported_claims') or [])
    cited = int(citation_check.get('cited_factual_claims') or 0)
    unsupported_rate = unsupported / max(1, cited + unsupported)
    accepted = ('SUCCEEDED', 'COMPLETED', 'PARTIAL')
    if case['answerable']:
        answerability_ok = run.status in accepted and bool(run.citations)
    else:
        answerability_ok = run.status in ('ABSTAINED', 'PARTIAL')
    retrieval_ok = recall >= 0.5 if terms else answerability_ok
    skills = list(run.skill_activations.values_list('skill_id', flat=True))
    steps = list(run.steps.values_list('step_type', flat=True))
    return {
        'case_id': case['case_id'],
        'task_type': case['task_type'],
        'query': case['query'],
        'answerable': case['answerable'],
        'run_id': run.run_id,
        'status': run.status,
        'stage': run.stage,
        'error_code': run.error_code,
        'evidence_count': run.evidence_count,
        'citations': len(run.citations or []),
        'artifact_count': run.artifacts.count(),
        'skills': skills,
        'steps': len(steps),
        'tool_calls': (run.metrics or {}).get('tool_calls', 0),
        'latency_ms': (run.metrics or {}).get('latency_ms', 0),
        'retrieval_recall': round(recall, 4),
        'mrr': round(_mrr(run, terms), 4),
        'citation_presence': bool(run.citations),
        'answerability_ok': answerability_ok,
        'retrieval_ok': retrieval_ok,
        'unsupported_claim_rate': round(unsupported_rate, 4),
        'unsupported_claims': citation_check.get('unsupported_claims') or [],
        'answer': run.answer_text,
        'citations_payload': run.citations,
        'steps_trace': list(run.steps.values(
            'step_id', 'step_type', 'decision', 'reason_code', 'latency_ms', 'tokens',
            'tool_calls', 'failure_code',
        )),
    }


def _p95(values):
    values = sorted(value for value in values if value is not None)
    if not values:
        return 0
    index = min(len(values) - 1, max(0, int(round(0.95 * (len(values) - 1)))))
    return values[index]


class Command(BaseCommand):
    help = 'Run the workbench development evaluation against seeded demo spaces.'

    def add_arguments(self, parser):
        parser.add_argument('--username', default='demo_student')
        parser.add_argument('--output', default=str(Path(settings.BASE_DIR) / 'tests/evaluation/workbench_results.json'))
        parser.add_argument('--limit', type=int, default=0)

    def handle(self, *args, **options):
        User = get_user_model()
        user = User.objects.filter(username=options['username'], is_active=True).first()
        if user is None:
            raise CommandError(f"演示账户不存在：{options['username']}。请先运行 seed_workbench_demo。")
        spaces = {workspace.name: workspace for workspace in Workspace.objects.filter(owner=user)}
        missing = sorted({case['workspace'] for case in CASES} - set(spaces))
        if missing:
            raise CommandError(f"缺少演示空间：{', '.join(missing)}。请先运行 seed_workbench_demo。")
        cases = list(CASES)
        if options['limit']:
            cases = cases[:options['limit']]
        results = []
        failures = []
        for case in cases:
            workspace = spaces[case['workspace']]
            try:
                run = create_task(
                    user, workspace, case['task_type'], case['query'],
                    requested_mode='standard', skip_rate_limit=True,
                )
                run.metrics = {**(run.metrics or {}), 'evaluation_case_id': case['case_id'], 'evaluation': True}
                run.save(update_fields=['metrics'])
                claim_next('evaluate-workbench')
                finished = execute_run(run.run_id, worker_id='evaluate-workbench')
                payload = _case_result(case, finished)
                results.append(payload)
                if not payload['answerability_ok'] or not payload['retrieval_ok']:
                    failures.append({
                        'case_id': case['case_id'],
                        'status': finished.status,
                        'error_code': finished.error_code,
                        'recall': payload['retrieval_recall'],
                        'answerability_ok': payload['answerability_ok'],
                        'retrieval_ok': payload['retrieval_ok'],
                    })
                self.stdout.write(
                    f"{case['case_id']}: {finished.status} recall={payload['retrieval_recall']:.2f} "
                    f"mrr={payload['mrr']:.2f} citations={payload['citations']}"
                )
            except Exception as exc:
                failures.append({'case_id': case['case_id'], 'error': type(exc).__name__,
                                 'code': getattr(exc, 'code', '')})
                self.stdout.write(self.style.ERROR(f"{case['case_id']}: ERROR {type(exc).__name__}"))
        answerable = [row for row in results if row['answerable']]
        latencies = [row['latency_ms'] for row in results]
        summary = {
            'case_count': len(results),
            'answerable_count': len(answerable),
            'unanswerable_count': len(results) - len(answerable),
            'retrieval_recall_mean': round(statistics.mean([row['retrieval_recall'] for row in answerable]), 4) if answerable else 0,
            'mrr_mean': round(statistics.mean([row['mrr'] for row in answerable]), 4) if answerable else 0,
            'citation_presence_rate': round(sum(row['citation_presence'] for row in results) / max(1, len(results)), 4),
            'citation_presence_rate_answerable': round(
                sum(row['citation_presence'] for row in answerable) / max(1, len(answerable)), 4
            ),
            'answerability_accuracy': round(sum(row['answerability_ok'] for row in results) / max(1, len(results)), 4),
            'unsupported_claim_rate_mean': round(statistics.mean([row['unsupported_claim_rate'] for row in results]), 4) if results else 0,
            'latency_p50_ms': int(statistics.median(latencies)) if latencies else 0,
            'latency_p95_ms': int(_p95(latencies)),
            'failed_cases': len(failures),
        }
        by_type = {}
        for row in results:
            bucket = by_type.setdefault(row['task_type'], {'count': 0, 'recall': [], 'answerability_ok': 0})
            bucket['count'] += 1
            bucket['recall'].append(row['retrieval_recall'])
            bucket['answerability_ok'] += int(row['answerability_ok'])
        summary['by_task_type'] = {
            key: {
                'count': value['count'],
                'recall_mean': round(statistics.mean(value['recall']), 4) if value['recall'] else 0,
                'answerability_accuracy': round(value['answerability_ok'] / max(1, value['count']), 4),
            }
            for key, value in by_type.items()
        }
        payload = {
            'generated_at': datetime.now(dt_timezone.utc).isoformat(),
            'status': 'COMPLETED_WITH_FINDINGS' if failures else 'COMPLETED',
            'git_sha': _git_sha(),
            'config_hash': _config_hash(),
            'dataset_hash': hashlib.sha256(json.dumps(CASES, sort_keys=True, ensure_ascii=False).encode('utf-8')).hexdigest(),
            'embedding': {
                'provider': getattr(settings, 'EMBEDDING_PROVIDER', ''),
                'model': getattr(settings, 'EMBEDDING_MODEL', ''),
                'revision': getattr(settings, 'EMBEDDING_REVISION', ''),
                'note': 'tfidf is a lexical baseline, not BGE semantic retrieval.'
                if getattr(settings, 'EMBEDDING_PROVIDER', '') == 'tfidf' else '',
            },
            'summary': summary,
            'failures': failures,
            'cases': results,
            'limitations': [
                '开发集为 11 条手写案例，规模小，不能作为泛化或论文结论。',
                '案例来源为本项目演示资料；未做多人独立标注与一致性检验。',
                '若 embedding_provider=tfidf，检索结论仅适用于该词法基线。',
                '代码分析未在隔离执行服务中运行测试，执行状态为 UNVERIFIED。',
            ],
        }
        output = Path(options['output'])
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
        self.stdout.write(self.style.SUCCESS(f"结果写入 {output}"))
        self.stdout.write(json.dumps(summary, ensure_ascii=False, indent=2))
