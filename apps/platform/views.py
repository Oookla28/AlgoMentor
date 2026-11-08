"""Platform admin console and machine-readable APIs."""

import time

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, render
from django.utils import timezone

from core.exceptions import BusinessError, ValidationError
from core.http import api_endpoint, json_body
from core.security.permissions import require_user

from .agent import AgentBudget, run_evidence_agent
from .capabilities import probe_capabilities
from .domains import get_domain_pack, list_domain_packs, list_task_packs, sync_manifests
from .models import AgentRun, EvaluationRun
from .tools import list_tool_specs


def _require_staff(user):
    require_user(user)
    if not user.is_staff:
        raise BusinessError('该操作仅限管理员。', code='PERMISSION_DENIED', status_code=403)


def _serialize_run(run, include_details=False):
    payload = {
        'run_id': run.run_id,
        'status': run.status,
        'domain': run.domain,
        'query': run.query,
        'mode': run.mode,
        'answer': run.answer_text,
        'citations': run.citations,
        'evidence_count': run.evidence_count,
        'step_count': run.step_count,
        'error_code': run.error_code,
        'metrics': run.metrics,
        'created_at': run.created_at.isoformat() if run.created_at else '',
        'finished_at': run.finished_at.isoformat() if run.finished_at else '',
    }
    if include_details:
        payload['steps'] = [
            {
                'step_id': step.step_id, 'parent_step_id': step.parent_step_id, 'hop_id': step.hop_id,
                'step_type': step.step_type, 'input_summary': step.input_summary,
                'output_summary': step.output_summary, 'evidence_ids': step.evidence_ids,
                'decision': step.decision, 'reason_code': step.reason_code,
                'latency_ms': step.latency_ms, 'tokens': step.tokens, 'tool_calls': step.tool_calls,
                'provider': step.provider, 'index_version': step.index_version,
                'model': step.model, 'failure_code': step.failure_code,
            }
            for step in run.steps.all()
        ]
        payload['evidence'] = [
            {
                'evidence_id': item.evidence_id, 'chunk_id': item.chunk_id, 'page': item.page,
                'heading_path': item.heading_path, 'content': item.content,
                'authority_score': item.authority_score, 'retrieval_score': item.retrieval_score,
                'source_uri': item.source_uri, 'content_hash': item.content_hash,
                'source_version': item.source_version,
            }
            for item in run.evidence.all().order_by('-retrieval_score')[:20]
        ]
        payload['claims'] = [
            {
                'claim_id': claim.claim_id, 'text': claim.text, 'polarity': claim.polarity,
                'numbers': claim.numbers, 'units': claim.units, 'versions': claim.versions,
                'years': claim.years, 'evidence_ids': claim.evidence_ids, 'status': claim.status,
            }
            for claim in run.claims.all()[:40]
        ]
        payload['conflicts'] = [
            {
                'conflict_id': conflict.conflict_id, 'conflict_type': conflict.conflict_type,
                'confidence': conflict.confidence, 'verdict': conflict.verdict,
                'claims': conflict.claims, 'explanation': conflict.explanation,
            }
            for conflict in run.conflict_sets.all()[:20]
        ]
    return payload


def _rate_limit(user):
    key = f'platform-agent-rate:{user.pk}:{int(time.time() // 60)}'
    count = cache.get(key, 0)
    if count >= 10:
        raise BusinessError('平台 Agent 请求过于频繁，请稍后再试。', code='RATE_LIMITED', status_code=429)
    cache.set(key, count + 1, 70)


@login_required
def console(request):
    if not request.user.is_staff:
        raise PermissionDenied
    context = {
        'page_title': '平台能力与 Agent 控制台',
        'capabilities': probe_capabilities(),
        'domain_packs': list_domain_packs(),
        'task_packs': list_task_packs(),
        'tools': list_tool_specs(),
        'runs': AgentRun.objects.order_by('-created_at')[:10],
        'evaluation_runs': EvaluationRun.objects.order_by('-created_at')[:5],
        'selected_run': None,
        'result': None,
        'error': '',
    }
    run_id = request.GET.get('run', '')
    if run_id:
        selected = AgentRun.objects.filter(run_id=run_id).first()
        if selected:
            context['selected_run'] = _serialize_run(selected, include_details=True)
    if request.method == 'POST':
        query = (request.POST.get('query') or '').strip()
        domain = (request.POST.get('domain') or 'data_structures').strip()
        try:
            _rate_limit(request.user)
            outcome = run_evidence_agent(request.user, query, domain=domain)
            run = AgentRun.objects.filter(run_id=outcome.run_id).first()
            context['result'] = _serialize_run(run, include_details=True) if run else outcome.to_dict()
        except BusinessError as exc:
            context['error'] = exc.message
        except Exception:
            context['error'] = '平台 Agent 执行失败，请稍后重试。'
    return render(request, 'platform/console.html', context)


@api_endpoint()
def capabilities_api(request):
    _require_staff(request.user)
    return {
        'capabilities': probe_capabilities(),
        'domain_packs': [pack.to_dict() for pack in list_domain_packs()],
        'task_packs': [task.to_dict() for task in list_task_packs()],
        'tools': list_tool_specs(),
        'generated_at': timezone.now().isoformat(),
    }


@api_endpoint()
def domains_api(request):
    return {
        'domain_packs': [pack.to_dict() for pack in list_domain_packs()],
        'task_packs': [task.to_dict() for task in list_task_packs()],
        'tools': list_tool_specs(),
    }


@api_endpoint(methods=('POST',))
def agent_run_api(request):
    if not getattr(settings, 'PLATFORM_AGENT_ENABLED', True):
        raise BusinessError('平台 Agent 当前未启用。', code='PLATFORM_AGENT_DISABLED', status_code=503)
    _rate_limit(request.user)
    body = json_body(request)
    query = (body.get('query') or '').strip()
    domain = (body.get('domain') or 'data_structures').strip()
    if get_domain_pack(domain) is None:
        raise ValidationError('未知领域知识包。', code='DOMAIN_PACK_NOT_FOUND')
    outcome = run_evidence_agent(request.user, query, domain=domain, mode=str(body.get('mode') or 'adaptive'))
    run = get_object_or_404(AgentRun, run_id=outcome.run_id)
    return _serialize_run(run, include_details=True)


@api_endpoint()
def run_detail_api(request, run_id):
    run = get_object_or_404(AgentRun, run_id=run_id)
    if not request.user.is_staff and run.user_id != request.user.pk:
        raise BusinessError('无权查看该 Agent 运行。', code='PERMISSION_DENIED', status_code=403)
    return _serialize_run(run, include_details=True)


@api_endpoint()
def runs_api(request):
    _require_staff(request.user)
    return {'runs': [_serialize_run(run) for run in AgentRun.objects.order_by('-created_at')[:30]]}


@api_endpoint(methods=('POST',))
def sync_domains_api(request):
    _require_staff(request.user)
    count = sync_manifests()
    return {'synced': count}
