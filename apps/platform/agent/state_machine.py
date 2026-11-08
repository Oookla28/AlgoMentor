"""Explicit, bounded evidence-grounded agent state machine.

Sequence:
START -> ROUTE -> PLAN -> RETRIEVE -> EVIDENCE_GATE
-> RETRIEVE_MORE/CALL_TOOL/CONFLICT_CHECK -> VERIFY -> ANSWER/ABSTAIN -> END

Only step summaries and decisions are persisted; full chain-of-thought is not.
"""

from dataclasses import asdict, dataclass, field
import json
import time
import uuid
from types import SimpleNamespace

from django.conf import settings
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from core.exceptions import BusinessError, ValidationError
from core.security.permissions import require_user

from apps.knowledge.services.citation_verifier import verify_answer
from apps.knowledge.services.claim_service import extract_claims
from apps.knowledge.services.conflict_service import detect_conflicts
from apps.knowledge.services.hierarchical_chunker import estimate_tokens
from apps.knowledge.services.query_router import route_query
from apps.knowledge.services.retrieval_service import Citation
from apps.knowledge.services.sparse_retrieval import tokenize
from apps.platform.capabilities import capability_map
from apps.platform.domains import get_domain_pack, list_task_packs
from apps.platform.models import AgentRun, AgentStep
from apps.platform.provenance import persist_claims, persist_conflicts, persist_evidence
from apps.platform.tools import execute_tool
from .adaptive_router import DEFAULT_WEIGHTS, RoutingState, choose_action


class BudgetExceeded(Exception):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


class RunCancelled(Exception):
    """Raised between steps when the owner cancels a queued/running task."""


@dataclass(frozen=True)
class AgentBudget:
    max_steps: int = 20
    max_tokens: int = 6000
    max_tool_calls: int = 8
    max_latency_ms: int = 30000
    max_retrieve_more: int = 2

    @classmethod
    def from_settings(cls):
        return cls(
            max_steps=getattr(settings, 'PLATFORM_AGENT_MAX_STEPS', 20),
            max_tokens=getattr(settings, 'PLATFORM_AGENT_MAX_TOKENS', 6000),
            max_tool_calls=getattr(settings, 'PLATFORM_AGENT_MAX_TOOL_CALLS', 8),
            max_latency_ms=getattr(settings, 'PLATFORM_AGENT_MAX_LATENCY_MS', 30000),
            max_retrieve_more=getattr(settings, 'PLATFORM_AGENT_MAX_RETRIEVE_MORE', 2),
        )


@dataclass
class GateResult:
    decision: str
    reason: str
    coverage: float
    support: float
    dense_support: float
    authority: float
    conflict_count: int
    claims: list = field(default_factory=list)
    conflicts: list = field(default_factory=list)

    def to_dict(self):
        return {
            'decision': self.decision,
            'reason': self.reason,
            'coverage': round(self.coverage, 4),
            'support': round(self.support, 4),
            'dense_support': round(self.dense_support, 4),
            'authority': round(self.authority, 4),
            'conflict_count': self.conflict_count,
        }


@dataclass
class AgentOutcome:
    run_id: str
    status: str
    answer: str
    citations: list
    evidence_count: int
    step_count: int
    metrics: dict

    def to_dict(self):
        return asdict(self)


def _summary(value, limit=500):
    if isinstance(value, str):
        text = value
    else:
        text = json.dumps(value, ensure_ascii=False, default=str)
    return text.replace('\n', ' ')[:limit]


def _content_terms(text):
    terms = {token for token in tokenize(text or '') if len(token) > 1}
    return terms or set(tokenize(text or ''))


def _dedupe(items):
    best = {}
    for item in items:
        chunk_id = item.get('chunk_id')
        if not chunk_id:
            continue
        if chunk_id not in best or float(item.get('retrieval_score', 0.0) or 0.0) > float(best[chunk_id].get('retrieval_score', 0.0) or 0.0):
            best[chunk_id] = item
    return sorted(best.values(), key=lambda item: (-float(item.get('retrieval_score', 0.0) or 0.0), item.get('chunk_id', '')))


def _claim_proxies(evidence_items):
    claims = []
    seen = set()
    seen_terms = []
    for item in evidence_items:
        for extracted in extract_claims(item.get('content', ''), item.get('chunk_id', '')):
            if extracted.predicate == '陈述' or len(extracted.subject.strip()) < 2:
                continue
            normalized = extracted.normalized_text.strip()
            terms = _content_terms(normalized)
            if not normalized or normalized in seen:
                continue
            if any(terms and old and len(terms & old) / len(terms | old) >= 0.9 for old in seen_terms):
                continue
            seen.add(normalized)
            seen_terms.append(terms)
            claims.append(SimpleNamespace(
                claim_id=extracted.claim_id,
                normalized_text=extracted.normalized_text,
                subject=extracted.subject,
                authority_level=int(item.get('authority_level', 3) or 3),
                detector_score=extracted.detector_score,
                source_chunk_id=item.get('chunk_id', ''),
                source_chunk=SimpleNamespace(chunk_id=item.get('chunk_id', '')),
                valid_from=parse_datetime(item['valid_from']) if item.get('valid_from') else None,
                valid_to=parse_datetime(item['valid_to']) if item.get('valid_to') else None,
                created_at=None,
            ))
    return claims


STAGE_BY_STEP = {
    'START': '读取资料',
    'ROUTE': '识别任务',
    'PLAN': '规划步骤',
    'RETRIEVE': '查找依据',
    'EVIDENCE_GATE': '核对证据',
    'RETRIEVE_MORE': '补充检索',
    'CALL_TOOL': '调用工具',
    'CONFLICT_CHECK': '检查冲突',
    'VERIFY': '核验引用',
    'ANSWER': '整理输出',
    'ABSTAIN': '已拒答',
    'FAILED': '执行失败',
    'END': '完成',
}


class StepRecorder:
    def __init__(self, run, budget, cancel_check=None, starting_index=0):
        self.run = run
        self.budget = budget
        self.cancel_check = cancel_check
        self.started = time.monotonic()
        self.step_index = max(0, int(starting_index or 0))
        self.tokens = 0
        self.tool_calls = 0
        self.last_step_id = ''

    def elapsed_ms(self):
        return int((time.monotonic() - self.started) * 1000)

    def check(self):
        if self.cancel_check is not None and self.cancel_check():
            raise RunCancelled()
        if self.step_index >= self.budget.max_steps:
            raise BudgetExceeded('STEP_BUDGET')
        if self.tokens >= self.budget.max_tokens:
            raise BudgetExceeded('TOKEN_BUDGET')
        if self.elapsed_ms() > self.budget.max_latency_ms:
            raise BudgetExceeded('LATENCY_BUDGET')

    def record(self, step_type, input_summary='', output_summary='', evidence_ids=(), decision='',
               reason_code='', provider='', index_version='', model='', failure_code='',
               tool_calls=0, hop_id=0, force=False):
        if not force:
            self.check()
        self.step_index += 1
        step_id = f'S{self.step_index:03d}'
        tokens = estimate_tokens(_summary(input_summary) + _summary(output_summary))
        self.tokens += tokens
        self.tool_calls += tool_calls
        row = AgentStep.objects.create(
            run=self.run, step_id=step_id, parent_step_id=self.last_step_id, hop_id=hop_id,
            step_type=step_type, input_summary=_summary(input_summary),
            output_summary=_summary(output_summary), evidence_ids=list(evidence_ids),
            decision=decision, reason_code=reason_code, latency_ms=self.elapsed_ms(),
            tokens=tokens, tool_calls=tool_calls, provider=provider,
            index_version=index_version, model=model, failure_code=failure_code,
        )
        self.last_step_id = step_id
        AgentRun.objects.filter(pk=self.run.pk).update(
            step_count=self.step_index,
            stage=STAGE_BY_STEP.get(step_type, self.run.stage),
        )
        return row


def _index_context():
    from apps.knowledge.models import KnowledgeDocument
    document = KnowledgeDocument.objects.exclude(latest_index_version='').order_by('-created_at').first()
    if document is not None:
        return document.latest_index_version, ((document.source_metadata or {}).get('advanced') or {}).get('embedding_dimension', 0), 'advanced'
    document = KnowledgeDocument.objects.exclude(index_version='').order_by('-created_at').first()
    if document is not None:
        return document.index_version, document.embedding_dimension, 'legacy'
    return '', 0, 'none'


def _run_tool(recorder, user, tool_id, args, provider, index_version, model, hop_id=0,
              scope_document_ids=None):
    if recorder.tool_calls >= recorder.budget.max_tool_calls:
        raise BudgetExceeded('TOOL_BUDGET')
    call_args = dict(args)
    if scope_document_ids is not None:
        call_args['document_ids'] = scope_document_ids
    result = execute_tool(tool_id, user, **call_args)
    recorder.record(
        'CALL_TOOL', input_summary={'tool': tool_id, 'args': args},
        output_summary={'ok': result.ok, 'evidence_ids': list(result.evidence_ids), 'message': result.message},
        evidence_ids=result.evidence_ids, decision='TOOL_OK' if result.ok else 'TOOL_FAILED',
        reason_code='TOOL_COMPLETED' if result.ok else result.failure_code,
        provider=provider, index_version=index_version, model=model,
        failure_code=result.failure_code, tool_calls=1, hop_id=hop_id,
    )
    items = []
    if result.ok:
        if isinstance(result.output.get('results'), list):
            items = result.output['results']
        elif isinstance(result.output.get('result'), dict):
            items = [result.output['result']]
    return result, items


def _evaluate_gate(query, evidence_items):
    items = _dedupe(evidence_items)
    if not items:
        return GateResult('ABSTAIN', 'NO_EVIDENCE', 0.0, 0.0, 0.0, 0.0, 0)
    query_terms = _content_terms(query)
    top = items[:6]
    evidence_terms = set()
    for item in top:
        evidence_terms |= _content_terms((item.get('content') or '') + ' ' + (item.get('heading_path') or ''))
    coverage = len(query_terms & evidence_terms) / max(1, len(query_terms))
    scores = [float(item.get('retrieval_score', 0.0) or 0.0) for item in items[:3]]
    support = sum(scores) / max(1, len(scores))
    dense_support = max([float(item.get('retrieval_score', 0.0) or 0.0) for item in items if item.get('retriever') == 'dense'] + [0.0])
    authority = max((1 - (int(item.get('authority_level', 3) or 3) - 1) / 4) for item in items)
    claims = _claim_proxies(items)
    conflicts = detect_conflicts(claims)
    min_coverage = getattr(settings, 'PLATFORM_GATE_MIN_COVERAGE', 0.15)
    min_dense = getattr(settings, 'EVIDENCE_RAG_MIN_DENSE_SUPPORT', 0.35)
    if coverage >= min_coverage or dense_support >= min_dense:
        return GateResult('PASS', 'EVIDENCE_SUFFICIENT', coverage, support, dense_support, authority, len(conflicts), claims, conflicts)
    return GateResult('RETRIEVE_MORE', 'LOW_COVERAGE', coverage, support, dense_support, authority, len(conflicts), claims, conflicts)


def _citation_from_item(item):
    return Citation(
        item.get('chunk_id', ''), item.get('document_name', ''), item.get('document_hash', ''),
        item.get('chapter', ''), item.get('section', ''), int(item.get('page') or 1),
        item.get('content', ''), item.get('source_type', 'original'), str(item.get('source_version', '1')),
        float(item.get('retrieval_score', 0.0) or 0.0), item.get('source_uri', ''),
        parent_chunk_id=item.get('parent_chunk_id', ''), heading_path=item.get('heading_path', ''),
        chunk_type=item.get('chunk_type', ''), char_start=item.get('char_start'),
        char_end=item.get('char_end'), evidence_id=f"chunk:{item.get('chunk_id', '')}",
        matched_content=item.get('content', ''), media_asset_id=item.get('media_asset_id', ''),
        start_time=item.get('start_time'), end_time=item.get('end_time'),
        authority_level=int(item.get('authority_level', 3) or 3), source_uri=item.get('source_uri', ''),
    )


def _citation_dict(citation):
    return {
        'chunk_id': citation.chunk_id, 'document_name': citation.document_name,
        'page_number': citation.page_number, 'content': citation.content,
        'source_type': citation.source_type, 'score': citation.score, 'url': citation.url,
        'parent_chunk_id': citation.parent_chunk_id, 'heading_path': citation.heading_path,
        'char_start': citation.char_start, 'char_end': citation.char_end,
        'evidence_id': citation.evidence_id, 'authority_level': citation.authority_level,
        'media_asset_id': citation.media_asset_id, 'start_time': citation.start_time,
        'end_time': citation.end_time,
    }


def _span_score(sentence, query_terms):
    terms = _content_terms(sentence)
    score = len(query_terms & terms) * 10 + min(len(sentence), 120) / 100
    if any(marker in sentence for marker in ('判满', '判空', '队满', '队空', 'rear', 'front', '==', '%')):
        score += 10
    if sentence.endswith(('如下', '：', ':')) or '相关操作' in sentence:
        score -= 5
    return score


def _best_span(content, query):
    query_terms = _content_terms(query)
    candidates = []
    for sentence in (content or '').replace('\r', '').replace('\n', '。').split('。'):
        sentence = sentence.strip(' ；;，,')
        if len(sentence) < 8 or len(sentence) > 240:
            continue
        if any(marker in sentence for marker in ('//', '{', '}', '#define', '#include', 'typedef', 'struct ')):
            continue
        candidates.append((_span_score(sentence, query_terms), sentence))
    if not candidates:
        return (content or '')[:200]
    candidates.sort(key=lambda pair: (-pair[0], pair[1]))
    return candidates[0][1]


def _select_spans(query, items, limit=2):
    query_terms = _content_terms(query)
    scored = []
    for item in items:
        span = _best_span(item.get('content', ''), query)
        score = _span_score(span, query_terms) + float(item.get('retrieval_score', 0.0) or 0.0)
        scored.append((score, item, span))
    scored.sort(key=lambda pair: (-pair[0], pair[1].get('chunk_id', '')))
    selected = []
    seen = set()
    for _score, item, span in scored:
        if item.get('chunk_id') in seen:
            continue
        selected.append((item, span))
        seen.add(item.get('chunk_id'))
        if len(selected) >= limit:
            break
    return selected


def _build_answer(query, gate, evidence_items):
    items = _dedupe(evidence_items)
    if not items or gate is None or gate.decision != 'PASS':
        return '当前资料没有提供充分证据，无法回答该问题。', [], gate
    claim_map = {claim.claim_id: claim for claim in gate.claims}
    if gate.conflicts:
        selected = []
        seen = set()
        for conflict in gate.conflicts[:2]:
            for claim_id in (conflict.claim_a_id, conflict.claim_b_id):
                claim = claim_map.get(claim_id)
                if claim is None:
                    continue
                item = next((row for row in items if row.get('chunk_id') == claim.source_chunk_id), None)
                if item and item['chunk_id'] not in seen:
                    selected.append(item)
                    seen.add(item['chunk_id'])
        if len(selected) >= 2:
            citations = [_citation_from_item(item) for item in selected[:3]]
            source_index = {citation.chunk_id: index for index, citation in enumerate(citations, 1)}
            parts = ['检索到互相冲突的证据，当前不能确定唯一答案。']
            for number, conflict in enumerate(gate.conflicts[:2], 1):
                claim_a = claim_map.get(conflict.claim_a_id)
                claim_b = claim_map.get(conflict.claim_b_id)
                if not claim_a or not claim_b:
                    continue
                a_index = source_index.get(claim_a.source_chunk_id, 1)
                b_index = source_index.get(claim_b.source_chunk_id, len(citations))
                parts.append(f'冲突 {number}：[来源{a_index}] {claim_a.normalized_text}；[来源{b_index}] {claim_b.normalized_text}。')
            return ' '.join(parts), citations, gate
    selected = _select_spans(query, items, limit=2)
    citations = [_citation_from_item(item) for item, _span in selected]
    parts = ['根据检索到的资料证据：']
    for index, (_item, span) in enumerate(selected, 1):
        parts.append(f'[来源{index}] {span}')
    return ' '.join(parts), citations, gate


def _workspace_index_context(workspace):
    from apps.knowledge.models import KnowledgeDocument
    from apps.workspace.services.documents import active_document_ids
    document = (
        KnowledgeDocument.objects.filter(pk__in=active_document_ids(workspace))
        .exclude(latest_index_version='').order_by('-created_at').first()
    )
    if document is not None:
        advanced = ((document.source_metadata or {}).get('advanced') or {})
        return document.latest_index_version, advanced.get('embedding_dimension', 0), 'advanced'
    document = (
        KnowledgeDocument.objects.filter(pk__in=active_document_ids(workspace))
        .exclude(index_version='').order_by('-created_at').first()
    )
    if document is not None:
        return document.index_version, document.embedding_dimension, 'legacy'
    return '', 0, 'none'


def run_evidence_agent(user, query, domain='data_structures', mode='adaptive', budget=None,
                       run=None, workspace=None, cancel_check=None):
    require_user(user)
    query = (query or '').strip()
    if not query or len(query) > 2000:
        raise ValidationError('问题须为 1 至 2000 字。')
    pack = get_domain_pack(domain)
    if pack is None:
        raise ValidationError('未知领域知识包。', code='DOMAIN_PACK_NOT_FOUND')
    if workspace is None and run is not None and run.workspace_id:
        workspace = run.workspace
    budget = budget or AgentBudget.from_settings()
    provider = getattr(settings, 'EMBEDDING_PROVIDER', '')
    model = getattr(settings, 'EMBEDDING_MODEL', '')
    if workspace is not None:
        index_version, dimension, index_kind = _workspace_index_context(workspace)
    else:
        index_version, dimension, index_kind = _index_context()
    caps = capability_map()
    scope_document_ids = None
    if workspace is not None:
        from apps.workspace.services.documents import active_document_ids
        scope_document_ids = active_document_ids(workspace)
    metrics = {
        'provider': provider, 'model': model, 'dimension': dimension,
        'index_version': index_version, 'index_kind': index_kind,
        'threshold': getattr(settings, 'PLATFORM_GATE_MIN_SUPPORT', 0.30),
        'tokens_estimated': True, 'capabilities': {name: entry['state'] for name, entry in caps.items()},
    }
    if workspace is not None:
        metrics['workspace_id'] = workspace.pk
        metrics['scope_document_count'] = len(scope_document_ids or [])
    if run is None:
        run = AgentRun.objects.create(
            run_id=uuid.uuid4().hex, user=user, domain=pack.pack_id, query=query, mode=mode,
            workspace=workspace, task_type='grounded_qa', status='RUNNING', stage='读取资料',
            budget=asdict(budget), metrics=metrics,
        )
    else:
        run.user = user
        run.domain = pack.pack_id
        run.query = query
        run.mode = mode
        run.workspace = workspace
        run.task_type = run.task_type or 'grounded_qa'
        run.status = 'RUNNING'
        run.stage = '读取资料'
        run.error_code = ''
        run.metrics = {**(run.metrics or {}), **metrics}
        run.save(update_fields=['user', 'domain', 'query', 'mode', 'workspace', 'task_type', 'status', 'stage', 'error_code', 'metrics'])
    recorder = StepRecorder(run, budget, cancel_check=cancel_check, starting_index=run.steps.count())
    evidence_items = []
    attempted = set()
    gate = None
    status = 'FAILED'
    answer = ''
    citation_dicts = []
    error_code = ''
    try:
        recorder.record('START', input_summary={'query': query, 'domain': pack.pack_id}, decision='BEGIN', provider=provider, index_version=index_version, model=model)
        route = route_query(query)
        tasks = list_task_packs(pack.pack_id)
        task = tasks[0] if tasks else None
        recorder.record('ROUTE', input_summary=route.to_dict(), output_summary={'pack': pack.pack_id, 'task': task.task_id if task else ''}, decision='ROUTED', reason_code='DOMAIN_PACK_SELECTED', provider=provider, index_version=index_version, model=model)
        planned = ['keyword_search']
        if (not route.is_short or route.has_code or route.possible_conflict
                or workspace is not None or 'semantic_retrieval' in pack.capabilities):
            planned.append('semantic_search')
        recorder.record('PLAN', input_summary={'route': route.to_dict()}, output_summary={'actions': planned}, decision='PLANNED', reason_code='INITIAL_RETRIEVAL', provider=provider, index_version=index_version, model=model)
        for tool_id in planned:
            result, items = _run_tool(recorder, user, tool_id, {'query': query, 'top_k': 10}, provider, index_version, model, hop_id=0, scope_document_ids=scope_document_ids)
            attempted.add(tool_id)
            if result.ok:
                evidence_items.extend(items)
        evidence_items = _dedupe(evidence_items)
        recorder.record('RETRIEVE', output_summary={'count': len(evidence_items)}, evidence_ids=[item['chunk_id'] for item in evidence_items], decision='EVIDENCE_COLLECTED', reason_code='INITIAL_RETRIEVAL_COMPLETE', provider=provider, index_version=index_version, model=model)
        gate = _evaluate_gate(query, evidence_items)
        recorder.record('EVIDENCE_GATE', output_summary=gate.to_dict(), evidence_ids=[item['chunk_id'] for item in evidence_items], decision=gate.decision, reason_code=gate.reason, provider=provider, index_version=index_version, model=model)

        loops = 0
        while gate.decision == 'RETRIEVE_MORE' and loops < budget.max_retrieve_more:
            state = RoutingState(
                query=query, evidence=evidence_items, attempted=attempted,
                coverage=gate.coverage, support=gate.support, dense_support=gate.dense_support,
                authority=gate.authority,
                conflict_count=gate.conflict_count, hop=loops,
                tool_calls=recorder.tool_calls, tokens=recorder.tokens,
                latency_ms=recorder.elapsed_ms(),
            )
            action, rationale = choose_action(state)
            if action is None:
                recorder.record('RETRIEVE_MORE', output_summary=rationale, decision='STOP', reason_code=rationale.get('reason', 'NO_ACTION'), provider=provider, index_version=index_version, model=model)
                break
            recorder.record('RETRIEVE_MORE', input_summary={'state': gate.to_dict()}, output_summary=rationale, decision=action.action_id, reason_code='ADAPTIVE_ACTION', provider=provider, index_version=index_version, model=model)
            result, items = _run_tool(recorder, user, action.tool_id, action.args, provider, index_version, model, hop_id=loops + 1, scope_document_ids=scope_document_ids)
            attempted.add(action.action_id)
            if result.ok:
                evidence_items = _dedupe(evidence_items + items)
            gate = _evaluate_gate(query, evidence_items)
            recorder.record('EVIDENCE_GATE', output_summary=gate.to_dict(), evidence_ids=[item['chunk_id'] for item in evidence_items], decision=gate.decision, reason_code=gate.reason, provider=provider, index_version=index_version, model=model)
            loops += 1

        evidence_rows = list(persist_evidence(run, evidence_items, provider, index_version).values())
        evidence_rows.sort(key=lambda row: -row.retrieval_score)
        claims = persist_claims(run, evidence_rows[:12])
        conflicts = persist_conflicts(run, gate.conflicts if gate else [])
        recorder.record('CONFLICT_CHECK', output_summary={'claims': len(claims), 'conflicts': len(conflicts)}, evidence_ids=[item['chunk_id'] for item in evidence_items], decision='CONFLICTS_FOUND' if conflicts else 'NO_CONFLICT', reason_code='CONFLICT_SCAN_COMPLETE', provider=provider, index_version=index_version, model=model)

        answer, citation_objects, gate = _build_answer(query, gate, evidence_items) if gate else ('当前资料没有提供充分证据，无法回答该问题。', [], None)
        citation_dicts = [_citation_dict(citation) for citation in citation_objects]
        verification = verify_answer(answer, citation_objects)
        recorder.record('VERIFY', output_summary=verification, evidence_ids=[citation.chunk_id for citation in citation_objects], decision='VERIFIED' if verification['passed'] else 'VERIFICATION_FAILED', reason_code='CITATION_CHECK', provider=provider, index_version=index_version, model=model)
        if gate is not None and gate.decision == 'PASS' and verification['passed']:
            status = 'COMPLETED'
            recorder.record('ANSWER', input_summary={'answer': answer}, output_summary={'citations': len(citation_dicts)}, evidence_ids=[citation.chunk_id for citation in citation_objects], decision='ANSWERED', reason_code='GROUNDED_ANSWER', provider=provider, index_version=index_version, model=model)
        else:
            status = 'ABSTAINED'
            if gate is None or gate.decision != 'PASS':
                error_code = 'EVIDENCE_GATE_ABSTAIN'
            else:
                error_code = 'CITATION_VERIFICATION_FAILED'
            recorder.record('ABSTAIN', input_summary={'gate': gate.to_dict() if gate else {}, 'verification': verification}, decision='ABSTAINED', reason_code=error_code, provider=provider, index_version=index_version, model=model)
        recorder.record('END', output_summary={'status': status}, decision='END', reason_code='RUN_FINISHED', provider=provider, index_version=index_version, model=model, force=True)
    except RunCancelled:
        status = 'CANCELLED'
        error_code = 'CANCELLED_BY_USER'
        answer = answer or '任务已取消，已保留完成步骤与已获取证据。'
        try:
            recorder.record('ABSTAIN', output_summary={'cancelled': True}, decision='CANCELLED', reason_code=error_code, provider=provider, index_version=index_version, model=model, force=True)
        except Exception:
            pass
    except BudgetExceeded as exc:
        status = 'ABSTAINED'
        error_code = f'BUDGET_EXCEEDED:{exc.code}'
        answer = '本次检索超出步骤、Token、工具或延迟预算，系统已停止并拒答。'
        try:
            recorder.record('ABSTAIN', output_summary={'budget': exc.code}, decision='ABSTAINED', reason_code=error_code, provider=provider, index_version=index_version, model=model, force=True)
        except Exception:
            pass
    except Exception as exc:
        status = 'FAILED'
        error_code = getattr(exc, 'code', type(exc).__name__)
        try:
            recorder.record('FAILED', output_summary={'error': type(exc).__name__}, decision='FAILED', reason_code=error_code, provider=provider, index_version=index_version, model=model, failure_code=error_code, force=True)
        except Exception:
            pass
    finally:
        final_status = 'SUCCEEDED' if status == 'COMPLETED' and run.workspace_id else status
        stage = '完成' if final_status in ('COMPLETED', 'SUCCEEDED') else '已取消' if final_status == 'CANCELLED' else '已拒答' if final_status == 'ABSTAINED' else '执行失败'
        run.status = final_status
        run.stage = stage
        run.answer_text = answer
        run.citations = citation_dicts
        run.evidence_count = len(evidence_items)
        run.step_count = recorder.step_index
        run.error_code = error_code
        run.metrics = {
            **(run.metrics or {}),
            'latency_ms': recorder.elapsed_ms(),
            'tool_calls': recorder.tool_calls,
            'tokens_estimated': recorder.tokens,
            'budget_used': {
                'steps': recorder.step_index,
                'tokens_estimated': recorder.tokens,
                'tool_calls': recorder.tool_calls,
                'latency_ms': recorder.elapsed_ms(),
            },
            'gate': gate.to_dict() if gate else {},
            'citation_check': verification if 'verification' in locals() else {},
            'conflicts': len(gate.conflicts) if gate else 0,
            'retrieve_more_loops': locals().get('loops', 0),
        }
        run.finished_at = timezone.now()
        run.save(update_fields=['status', 'stage', 'answer_text', 'citations', 'evidence_count', 'step_count', 'error_code', 'metrics', 'finished_at'])
    return AgentOutcome(run.run_id, final_status, answer, citation_dicts, len(evidence_items), recorder.step_index, run.metrics)
