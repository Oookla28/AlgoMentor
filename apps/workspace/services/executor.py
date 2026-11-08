"""Task executors for the workbench.

All read paths are scoped to the workspace. Comparison and code analysis are
extractive: they only state what a retrieved span supports, mark missing fields
and never pretend to have executed user code.
"""

from dataclasses import asdict
from pathlib import Path
import re
import time

from django.conf import settings
from django.utils import timezone

from apps.knowledge.models import KnowledgeChunk, KnowledgeDocument
from apps.knowledge.services.citation_verifier import verify_answer
from apps.knowledge.services.sparse_retrieval import tokenize
from apps.platform.agent.state_machine import (
    AgentBudget, BudgetExceeded, RunCancelled, StepRecorder,
    _citation_dict, _citation_from_item, _run_tool, run_evidence_agent,
)
from apps.platform.capabilities import capability_map
from apps.platform.domains import get_domain_pack, get_task_pack
from apps.platform.models import AgentRun
from apps.platform.provenance import persist_claims, persist_evidence
from apps.platform.skills import activate_skill, resolve_tool_scope, select_skills
from apps.platform.tools import list_tool_specs

from ..models import WorkspaceDocument
from .artifacts import create_artifact, markdown_to_html
from .documents import active_document_ids

TASK_TYPES = ('grounded_qa', 'guided_learning', 'paper_comparison', 'code_investigation')

PRESETS = {
    'quick': AgentBudget(max_steps=12, max_tokens=3000, max_tool_calls=5, max_latency_ms=20000, max_retrieve_more=1),
    'standard': AgentBudget(max_steps=24, max_tokens=6000, max_tool_calls=10, max_latency_ms=45000, max_retrieve_more=2),
    'deep': AgentBudget(max_steps=36, max_tokens=10000, max_tool_calls=16, max_latency_ms=90000, max_retrieve_more=2),
}

COMPARISON_CUES = ('比较', '对比', '差异', '区别', 'compare', 'comparison')
GENERIC_QUERY_TERMS = {
    '论文', '文献', '文章', '实验', '结果', '报告', '研究', '这些', '什么', '如何', '是否',
    '方法', '结论', '局限', '数据集', '作者', '本文',
}
CODE_QUERY_CUES = (
    '代码', '函数', '类', '实现', '库存', '扣减', '异常', '错误', '空值', 'none', 'null',
    '风险', '补丁', 'bug', '测试', '变量', '循环', '条件', '安全', '密钥', '密码', '命令',
)

PAPER_FIELDS = (
    ('method', '方法', ('方法', '模型', '架构', '算法', '设计', 'approach', 'method', 'architecture')),
    ('experiment', '实验条件', ('数据集', '实验', '评价', '指标', '基线', 'dataset', 'baseline', 'experiment')),
    ('conclusion', '主要结论', ('结论', '结果', '表明', '发现', 'conclusion', 'result', 'outperform')),
    ('limitation', '局限', ('局限', '不足', '未来工作', '限制', 'limitation', 'future work')),
)

CODE_PATTERNS = (
    ('bare_except', re.compile(r'except\s*(?:Exception)?\s*:\s*$', re.I), '捕获了过宽异常'),
    ('swallowed_exception', re.compile(r'^\s*pass\s*$'), '异常被静默吞掉'),
    ('eval_exec', re.compile(r'\b(eval|exec)\s*\(', re.I), '动态执行字符串'),
    ('shell_call', re.compile(r'\b(subprocess|os\.system|os\.popen)\b', re.I), '外部命令调用'),
    ('todo', re.compile(r'\b(TODO|FIXME|XXX)\b', re.I), '未完成标记'),
    ('none_eq', re.compile(r'==\s*None|!=\s*None'), 'None 比较写法'),
    ('mutable_default', re.compile(r'def\s+\w+\([^)]*=\s*(\[\]|\{\})\s*[,)]'), '可变默认参数'),
    ('hardcoded_secret', re.compile(r'(password|secret|api[_-]?key)\s*=\s*[\'"][^\'"]{4,}', re.I), '疑似硬编码凭据'),
)


def budget_for(mode):
    return PRESETS.get(str(mode or 'standard'), PRESETS['standard'])


def _cancel_requested(run):
    return AgentRun.objects.filter(pk=run.pk, cancel_requested=True).values_list('id', flat=True).exists()


def _active_documents(workspace):
    ids = active_document_ids(workspace)
    return list(KnowledgeDocument.objects.filter(pk__in=ids).order_by('created_at', 'pk'))


def _dedupe(items):
    best = {}
    for item in items or []:
        chunk_id = item.get('chunk_id')
        if not chunk_id:
            continue
        if chunk_id not in best or float(item.get('retrieval_score', 0) or 0) > float(best[chunk_id].get('retrieval_score', 0) or 0):
            best[chunk_id] = item
    return sorted(best.values(), key=lambda row: (-float(row.get('retrieval_score', 0) or 0), row.get('chunk_id', '')))


def _prepare_skills(run):
    task_pack = get_task_pack(run.task_type, run.domain)
    domain_pack = get_domain_pack(run.domain)
    if task_pack is None or domain_pack is None:
        return [], task_pack, domain_pack
    enabled = {spec['tool_id'] for spec in list_tool_specs() if spec.get('enabled', True)}
    selected = select_skills(run.task_type, run.domain, run.query, attempts=run.attempts)
    prepared = []
    for skill in selected:
        scope = resolve_tool_scope(task_pack, domain_pack, skill, enabled)
        try:
            loaded, _activation = activate_skill(
                run, skill, f'task_type={run.task_type};domain={run.domain}', scope,
            )
            prepared.append((skill, loaded, scope))
        except Exception:
            # A broken Skill must not block the base task path.
            continue
    return prepared, task_pack, domain_pack


def _record_skill_step(recorder, prepared):
    if not prepared:
        recorder.record('SKILL', output_summary={'activated': 0, 'fallback': 'BASE_TASK_PATH'},
                        decision='SKILL_SKIPPED', reason_code='NO_SKILL_MATCH')
        return
    recorder.record(
        'SKILL',
        output_summary={
            'skills': [skill.skill_id for skill, _loaded, _scope in prepared],
            'versions': [skill.version for skill, _loaded, _scope in prepared],
            'tool_scope': sorted({tool for _skill, _loaded, scope in prepared for tool in scope}),
        },
        decision='SKILLS_ACTIVATED', reason_code='PROGRESSIVE_SKILL_LOAD',
    )


def _search(recorder, user, run, query, document_ids, top_k=12):
    provider = (run.metrics or {}).get('provider', getattr(settings, 'EMBEDDING_PROVIDER', ''))
    model = (run.metrics or {}).get('model', getattr(settings, 'EMBEDDING_MODEL', ''))
    index_version = (run.metrics or {}).get('index_version', '')
    items = []
    _result, keyword_items = _run_tool(
        recorder, user, 'keyword_search', {'query': query, 'top_k': top_k},
        provider, index_version, model, hop_id=0, scope_document_ids=document_ids,
    )
    items.extend(keyword_items)
    _semantic, semantic_items = _run_tool(
        recorder, user, 'semantic_search', {'query': query, 'top_k': max(4, top_k // 2)},
        provider, index_version, model, hop_id=0, scope_document_ids=document_ids,
    )
    items.extend(semantic_items)
    return _dedupe(items)


def _sentences(text):
    parts = re.split(r'(?<=[。！？；;])|\n+', str(text or ''))
    return [part.strip(' \t-*·') for part in parts if 8 <= len(part.strip()) <= 260]


def _section_paragraph(content, labels):
    lines = str(content or '').replace('\r', '').split('\n')
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped.startswith('#') or not any(label in stripped for label in labels):
            continue
        paragraph = []
        for following in lines[index + 1:]:
            if following.strip().startswith('#'):
                break
            if following.strip():
                paragraph.append(following.strip())
        if paragraph:
            return ' '.join(paragraph)
    return ''


def _best_sentence(items, cues, query_terms, require_cue=True, section_labels=()):
    best = None
    best_score = 0.0
    for item in items:
        if section_labels:
            paragraph = _section_paragraph(item.get('content', ''), section_labels)
            if paragraph:
                return paragraph, item
        for sentence in _sentences(item.get('content', '')):
            cue_hits = sum(1 for cue in cues if cue.lower() in sentence.lower())
            terms = {token for token in tokenize(sentence) if len(token) > 1}
            overlap = len(terms & query_terms) / max(1, len(terms | query_terms))
            if require_cue and cue_hits == 0:
                continue
            score = cue_hits * 2.0 + overlap * 3.0 + min(len(sentence), 120) / 240
            if score > best_score:
                best_score = score
                best = (sentence, item)
    return best


def _trim(text, limit=220):
    text = re.sub(r'\s+', ' ', str(text or '')).strip()
    return text if len(text) <= limit else text[:limit].rstrip() + '…'


def _citation_list(items):
    ordered = []
    seen = set()
    for item in items:
        chunk_id = item.get('chunk_id')
        if not chunk_id or chunk_id in seen:
            continue
        seen.add(chunk_id)
        ordered.append(item)
    return ordered, [_citation_from_item(item) for item in ordered]


def _persist(run, items):
    provider = (run.metrics or {}).get('provider', '')
    index_version = (run.metrics or {}).get('index_version', '')
    rows = list(persist_evidence(run, items, provider, index_version).values())
    rows.sort(key=lambda row: -row.retrieval_score)
    if rows:
        persist_claims(run, rows[:12])
    return rows


def _finish(run, status, stage, answer, citations, evidence_count, error_code='', metrics=None):
    run.status = status
    run.stage = stage
    run.answer_text = answer
    run.citations = citations
    run.evidence_count = evidence_count
    run.error_code = error_code
    run.metrics = {**(run.metrics or {}), **(metrics or {})}
    run.finished_at = timezone.now()
    run.save(update_fields=[
        'status', 'stage', 'answer_text', 'citations', 'evidence_count',
        'error_code', 'metrics', 'finished_at',
    ])


def _base_metrics(run, recorder):
    return {
        'latency_ms': recorder.elapsed_ms(),
        'tokens_estimated': recorder.tokens,
        'tool_calls': recorder.tool_calls,
        'budget_used': {
            'steps': recorder.step_index,
            'tokens_estimated': recorder.tokens,
            'tool_calls': recorder.tool_calls,
            'latency_ms': recorder.elapsed_ms(),
        },
        'task_type': run.task_type,
        'workspace_id': run.workspace_id,
        'execution_mode': 'worker',
    }


def _abstain(recorder, run, reason, message, status='ABSTAINED'):
    recorder.record('ABSTAIN', output_summary={'reason': reason}, decision='ABSTAINED', reason_code=reason, force=True)
    recorder.record('END', output_summary={'status': status}, decision='END', reason_code='RUN_FINISHED', force=True)
    _finish(run, status, '已拒答' if status == 'ABSTAINED' else '部分完成', message, [], 0, reason, _base_metrics(run, recorder))


def run_guided_learning(run, user, recorder, prepared):
    workspace = run.workspace
    documents = _active_documents(workspace)
    if not documents:
        return _abstain(recorder, run, 'WORKSPACE_EMPTY', '当前空间没有可检索资料，请先上传学习材料。')
    scope = [document.pk for document in documents]
    items = _search(recorder, user, run, f'{run.query} 定义 条件 方法 例子', scope, top_k=10)
    recorder.record('RETRIEVE', output_summary={'count': len(items)}, evidence_ids=[item.get('chunk_id') for item in items],
                    decision='EVIDENCE_COLLECTED', reason_code='WORKSPACE_SCOPED_RETRIEVAL')
    if not items:
        return _abstain(recorder, run, 'NO_EVIDENCE', '当前资料没有检索到与该学习目标相关的证据。')
    used, citations = _citation_list(items[:4])
    citation_index = {item['chunk_id']: index for index, item in enumerate(used, 1)}
    outline = []
    seen_headings = set()
    for item in used:
        heading = (item.get('heading_path') or item.get('section') or item.get('document_name') or '').split('>')[-1].strip()
        if not heading or heading in seen_headings:
            continue
        seen_headings.add(heading)
        outline.append((heading, item))
        if len(outline) >= 4:
            break
    if not outline:
        outline = [('资料要点', used[0])]
    query_terms = {token for token in tokenize(run.query) if len(token) > 1}
    hints = []
    for _heading, item in outline[:3]:
        sentence = _best_sentence([item], ('是', '指', '条件', '方法', '为'), query_terms, require_cue=False)
        if sentence:
            hints.append((sentence[0], item))
    top_sentence = _best_sentence(used, ('是', '指', '为', '条件', '方法'), query_terms, require_cue=False)
    self_check = top_sentence[0] if top_sentence else _trim(used[0].get('content', ''))
    lines = [
        f'# 学习提纲：{run.query}',
        '',
        '> 说明：本提纲由空间资料抽取生成；自测题是自动构造，不是正式题库，也不更新掌握度。',
        '',
        '## 学习目标拆解',
        f'- 理解：{_trim(run.query, 80)}',
        '- 能指出关键条件与适用场景，并能回到原文核对。',
        '',
        '## 分层提纲',
    ]
    for heading, item in outline:
        marker = f"[来源{citation_index.get(item['chunk_id'], 1)}]"
        lines.append(f'- **{_trim(heading, 60)}**：{_trim(item.get("content", ""), 140)} {marker}')
    lines.extend(['', '## 分层提示'])
    for index, (hint, item) in enumerate(hints, 1):
        marker = f"[来源{citation_index.get(item['chunk_id'], 1)}]"
        lines.append(f'{index}. 提示：先找出「{_trim(hint, 90)}」中的关键词与条件。{marker}')
    lines.extend([
        '', '## 自测（自动构造，非正式题库）',
        f'请用自己的话解释：**{_trim(run.query, 100)}**，并指出一个适用条件。',
        f'参考要点：{_trim(self_check, 180)} [来源{citation_index.get(used[0]["chunk_id"], 1)}]',
        '', '## 下一步',
        '- 回到来源核对原文，再尝试用一句话总结。',
        '- 本结果不替代课程判题成绩，也不会自动提高能力分数。',
    ])
    markdown = '\n'.join(lines)
    create_artifact(run, 'learning_outline', 'guided-learning.md', markdown, 'markdown')
    create_artifact(run, 'learning_outline', 'guided-learning.html', markdown_to_html(f'学习提纲：{run.query}', markdown), 'html')
    answer = (
        f'已根据空间资料生成学习提纲，覆盖 {len(outline)} 个主题。'
        f'[来源1] {_trim(outline[0][1].get("content", ""), 120)} '
        '自测题由自动规则构造，不是正式题库，也不会更新课程掌握度。'
    )
    verification = verify_answer(answer, citations)
    recorder.record('VERIFY', output_summary=verification, evidence_ids=[item['chunk_id'] for item in used],
                    decision='VERIFIED' if verification['passed'] else 'VERIFICATION_PARTIAL', reason_code='CITATION_CHECK')
    recorder.record('ANSWER', output_summary={'artifact': 'guided-learning.md'}, evidence_ids=[item['chunk_id'] for item in used],
                    decision='ANSWERED', reason_code='GUIDED_LEARNING_ARTIFACT')
    recorder.record('END', output_summary={'status': 'SUCCEEDED'}, decision='END', reason_code='RUN_FINISHED', force=True)
    _persist(run, items)
    _finish(
        run, 'SUCCEEDED', '完成', answer, [_citation_dict(citation) for citation in citations],
        len(items), '', {**_base_metrics(run, recorder), 'citation_check': verification, 'outline_items': len(outline)},
    )


def run_paper_comparison(run, user, recorder, prepared):
    documents = _active_documents(run.workspace)
    if len(documents) < 2:
        return _abstain(recorder, run, 'INSUFFICIENT_DOCUMENTS',
                        '文献比较至少需要两篇可检索文献。当前空间可用文献不足，请补充上传。')
    documents = documents[:5]
    query_terms = {token for token in tokenize(run.query) if len(token) > 1}
    cells = {}
    all_items = []
    document_items = {}
    for document in documents:
        items = _search(
            recorder, user, run,
            f'{run.query} 方法 实验 数据集 评价指标 结论 局限',
            [document.pk], top_k=10,
        )
        if items:
            # Small2Big: a child span often stops before conclusion/limitations.
            _parent_result, parent_items = _run_tool(
                recorder, user, 'read_parent', {'chunk_id': items[0]['chunk_id']},
                (run.metrics or {}).get('provider', ''), (run.metrics or {}).get('index_version', ''),
                (run.metrics or {}).get('model', ''), hop_id=0, scope_document_ids=[document.pk],
            )
            items = _dedupe(items + parent_items)
        document_items[document.pk] = items
        all_items.extend(items)
        cells[document.pk] = {}
        for key, label, cues in PAPER_FIELDS:
            cells[document.pk][key] = _best_sentence(
                items, cues, query_terms, section_labels=(label,),
            )
    all_items = _dedupe(all_items)
    if all_items and not any(cue in run.query.lower() for cue in COMPARISON_CUES):
        evidence_terms = set()
        for item in all_items:
            evidence_terms |= {token for token in tokenize(item.get('content', '')) if len(token) > 1}
        specific_terms = {term for term in query_terms if term not in GENERIC_QUERY_TERMS}
        if specific_terms and not (specific_terms & evidence_terms):
            return _abstain(
                recorder, run, 'QUERY_NOT_SUPPORTED',
                '当前文献没有检索到与该具体问题相关的证据；未把无关文献强行拼成比较结论。',
            )
    qualifying = [document for document in documents if any(cells[document.pk][key] for key, _label, _cues in PAPER_FIELDS)]
    if len(qualifying) < 2:
        return _abstain(recorder, run, 'INSUFFICIENT_EVIDENCE',
                        '至少需要两篇文献提供可核验正文；当前只有摘要或证据不足，未生成对照表。',
                        status='PARTIAL')
    used, citations = _citation_list(all_items)
    citation_index = {item['chunk_id']: index for index, item in enumerate(used, 1)}
    lines = [
        f'# 文献比较：{run.query}',
        '',
        f'> 范围：本工作空间内 {len(qualifying)} 篇可检索文献的字段比较，不是系统综述。'
        '缺失字段表示当前正文未获得，不代表原文一定未报告。',
        '',
        '| 文献 | 方法 | 实验条件 | 主要结论 | 局限 |',
        '| --- | --- | --- | --- | --- |',
    ]
    missing = []
    for document in qualifying:
        row = [document.name]
        for key, label, _cues in PAPER_FIELDS:
            cell = cells[document.pk][key]
            if cell is None:
                row.append('未获得/未报告')
                missing.append(f'{document.name} · {label}')
            else:
                sentence, item = cell
                marker = f"[来源{citation_index.get(item['chunk_id'], 1)}]"
                row.append(f'{_trim(sentence, 150)} {marker}')
        lines.append('| ' + ' | '.join(row) + ' |')
    lines.extend(['', '## 比较边界'])
    for document in documents:
        if document not in qualifying:
            lines.append(f'- {document.name}：可用正文证据不足，未纳入主表。')
    lines.append('- 不同论文的数据集规模、基线、评价口径与计算预算可能不同，不能只按表格数字排序。')
    if missing:
        lines.append('- 缺失字段：' + '；'.join(missing[:12]))
    lines.extend(['', '## 下一步', '- 回到来源逐条核对实验设置；如需系统综述，需要明确的检索协议与覆盖记录。'])
    markdown = '\n'.join(lines)
    create_artifact(run, 'comparison', 'paper-comparison.md', markdown, 'markdown')
    create_artifact(run, 'comparison', 'paper-comparison.html', markdown_to_html(f'文献比较：{run.query}', markdown), 'html')
    first = used[0]
    answer = (
        f'已完成 {len(qualifying)} 篇文献的范围比较。'
        f'[来源{citation_index.get(first["chunk_id"], 1)}] {_trim(first.get("content", ""), 120)} '
        '缺失字段已在报告中标注；该结果不是系统综述，也不代表对未上传全文的论文作出判断。'
    )
    verification = verify_answer(answer, citations)
    recorder.record('VERIFY', output_summary=verification, evidence_ids=[item['chunk_id'] for item in used],
                    decision='VERIFIED' if verification['passed'] else 'VERIFICATION_PARTIAL', reason_code='CITATION_CHECK')
    recorder.record('ANSWER', output_summary={'artifact': 'paper-comparison.md'}, evidence_ids=[item['chunk_id'] for item in used],
                    decision='ANSWERED', reason_code='COMPARISON_ARTIFACT')
    recorder.record('END', output_summary={'status': 'SUCCEEDED'}, decision='END', reason_code='RUN_FINISHED', force=True)
    _persist(run, all_items)
    status = 'SUCCEEDED' if verification['passed'] else 'PARTIAL'
    _finish(
        run, status, '完成' if status == 'SUCCEEDED' else '部分完成', answer,
        [_citation_dict(citation) for citation in citations], len(all_items),
        '' if status == 'SUCCEEDED' else 'CITATION_VERIFICATION_PARTIAL',
        {**_base_metrics(run, recorder), 'citation_check': verification, 'documents_compared': len(qualifying), 'missing_fields': len(missing)},
    )


def _safe_text_document(document):
    path = Path(document.path or '')
    try:
        resolved = path.resolve()
    except OSError:
        return ''
    roots = [Path(settings.EVIDENCE_RAG_UPLOAD_DIR).resolve(), Path(settings.BASE_DIR).resolve()]
    if not any(root == resolved or root in resolved.parents for root in roots):
        return ''
    if resolved.suffix.lower() not in {'.py', '.java', '.c', '.cpp', '.h', '.js', '.ts', '.md', '.txt', '.json', '.yaml', '.yml'}:
        return ''
    if not resolved.is_file() or resolved.stat().st_size > 2 * 1024 * 1024:
        return ''
    try:
        return resolved.read_text(encoding='utf-8', errors='replace')
    except OSError:
        return ''


def _suggested_diff(document, text, pattern):
    lines = text.splitlines()
    changes = []
    for number, line in enumerate(lines, 1):
        if pattern['kind'] == 'none_eq':
            if ' == None' in line:
                changes.append((number, line, line.replace(' == None', ' is None')))
            elif ' != None' in line:
                changes.append((number, line, line.replace(' != None', ' is not None')))
        elif pattern['kind'] == 'swallowed_exception':
            if number < len(lines) and re.match(r'^\s*pass\s*$', lines[number]):
                indent = re.match(r'^(\s*)', line).group(1)
                changes.append((number + 1, lines[number], f'{indent}    raise'))
    if not changes:
        return ''
    chunks = [f'--- a/{document.name}\n+++ b/{document.name}\n']
    for number, old, new in changes[:6]:
        chunks.append(f'@@ -{number},1 +{number},1 @@\n-{old}\n+{new}\n')
    return '\n'.join(chunks)


def run_code_investigation(run, user, recorder, prepared):
    documents = _active_documents(run.workspace)
    if not documents:
        return _abstain(recorder, run, 'WORKSPACE_EMPTY', '当前空间没有可分析的代码或文档。')
    scope = [document.pk for document in documents]
    items = _search(recorder, user, run, f'{run.query} 函数 类 条件 异常 测试', scope, top_k=16)
    code_intent = any(cue in run.query.lower() for cue in CODE_QUERY_CUES)
    if code_intent:
        # Code text is mostly English identifiers; a Chinese question may miss it.
        # Add a bounded read-only scan of this workspace only (never another space).
        from apps.platform.tools.knowledge_tools import _payload
        rows = list(
            KnowledgeChunk.objects.filter(document_id__in=scope, is_active=True)
            .exclude(chunk_type='parent').order_by('document_id', 'page_number', 'chunk_id')[:24]
        )
        scanned = [
            {**_payload(row), 'retrieval_score': 0.0, 'retriever': 'scope_scan', 'rank': index + 1}
            for index, row in enumerate(rows)
        ]
        items = _dedupe(items + scanned)
        recorder.record('RETRIEVE', output_summary={'count': len(items), 'scan': len(scanned)},
                        evidence_ids=[item.get('chunk_id') for item in items],
                        decision='SCOPED_SCAN', reason_code='CODE_INTENT_SCAN')
    else:
        recorder.record('RETRIEVE', output_summary={'count': len(items)}, evidence_ids=[item.get('chunk_id') for item in items],
                        decision='EVIDENCE_COLLECTED', reason_code='WORKSPACE_SCOPED_RETRIEVAL')
        if items:
            evidence_terms = set()
            for item in items:
                evidence_terms |= {token for token in tokenize(item.get('content', '')) if len(token) > 1}
            query_terms = {token for token in tokenize(run.query) if len(token) > 1}
            specific = query_terms - GENERIC_QUERY_TERMS - {'项目', '使用', '部署', '是否', '什么', '如何'}
            if specific and not (specific & evidence_terms):
                return _abstain(
                    recorder, run, 'CODE_QUERY_NOT_SUPPORTED',
                    '当前代码资料没有检索到与该具体问题相关的证据；未把无关文件强行拼成分析结论。',
                )
    if not items:
        return _abstain(recorder, run, 'NO_EVIDENCE', '当前资料没有检索到与该代码问题相关的证据。')
    used, citations = _citation_list(items[:8])
    citation_index = {item['chunk_id']: index for index, item in enumerate(used, 1)}
    findings = []
    diffs = []
    inspected_docs = set()
    for item in used:
        document = next((doc for doc in documents if doc.pk == item.get('document_id')), None)
        if document is None:
            continue
        text = _safe_text_document(document)
        if not text:
            lines = (item.get('content') or '').splitlines()
            for number, line in enumerate(lines, 1):
                for kind, regex, label in CODE_PATTERNS:
                    if regex.search(line):
                        findings.append((document.name, number, line.strip(), label, item))
                        break
            continue
        inspected_docs.add(document.pk)
        for number, line in enumerate(text.splitlines(), 1):
            for kind, regex, label in CODE_PATTERNS:
                if regex.search(line):
                    findings.append((document.name, number, line.strip(), label, item))
                    if kind in ('none_eq', 'swallowed_exception', 'bare_except'):
                        diff = _suggested_diff(document, text, {'kind': 'swallowed_exception' if kind == 'bare_except' else kind})
                        if diff and diff not in diffs:
                            diffs.append(diff)
                    break
    capabilities = capability_map()
    execution = 'UNVERIFIED'
    execution_reason = '产品未提供隔离执行工具；未在主机运行用户代码。'
    if capabilities.get('piston', {}).get('state') == 'available':
        execution_reason = '本机 Piston 端口开放，但产品任务未获授权执行用户代码，因此仍未运行。'
    lines = [
        f'# 代码问题分析：{run.query}',
        '',
        '> 只读分析。建议 diff 仅作为文本产物，不会自动应用，也不会覆盖用户工程。',
        '',
        '## 涉及文件与证据',
    ]
    if findings:
        for name, number, line, label, item in findings[:20]:
            marker = f"[来源{citation_index.get(item['chunk_id'], 1)}]"
            lines.append(f'- **{name}:{number}** · {label} · `{_trim(line, 120)}` {marker}')
    else:
        lines.append('- 未发现可自动识别的风险模式。这不等于代码正确，需要人工审查与运行测试。')
    lines.extend([
        '', '## 建议补丁',
        '```diff',
        '\n'.join(diffs) if diffs else '# 未生成可自动构造的最小 diff；请人工确认修改点。',
        '```',
        '', '## 执行与验证状态',
        f'- 执行状态：**{execution}**',
        f'- 原因：{execution_reason}',
        '- 未运行测试，因此不能声称缺陷已修复。',
        '', '## 风险与下一步',
        '- 应用补丁前先确认调用方、错误处理语义与兼容性。',
        '- 如需运行测试，应由获授权的隔离执行环境完成；当前结果仅为静态证据。',
    ])
    markdown = '\n'.join(lines)
    create_artifact(run, 'code_report', 'code-investigation.md', markdown, 'markdown')
    create_artifact(run, 'code_report', 'code-investigation.html', markdown_to_html(f'代码问题分析：{run.query}', markdown), 'html')
    if diffs:
        create_artifact(run, 'suggested_patch', 'suggested.patch', '\n'.join(diffs), 'diff')
    first = used[0]
    answer = (
        f'已完成只读代码分析，发现 {len(findings)} 个需要人工确认的风险模式。'
        f'[来源{citation_index.get(first["chunk_id"], 1)}] {_trim(first.get("content", ""), 120)} '
        f'建议 diff 未应用；执行状态为 {execution}，未运行测试。'
    )
    verification = verify_answer(answer, citations)
    recorder.record('VERIFY', output_summary=verification, evidence_ids=[item['chunk_id'] for item in used],
                    decision='VERIFIED' if verification['passed'] else 'VERIFICATION_PARTIAL', reason_code='CITATION_CHECK')
    recorder.record('ANSWER', output_summary={'findings': len(findings), 'diffs': len(diffs)}, evidence_ids=[item['chunk_id'] for item in used],
                    decision='ANSWERED', reason_code='CODE_INVESTIGATION_ARTIFACT')
    recorder.record('END', output_summary={'status': 'SUCCEEDED'}, decision='END', reason_code='RUN_FINISHED', force=True)
    _persist(run, items)
    status = 'SUCCEEDED' if verification['passed'] else 'PARTIAL'
    _finish(
        run, status, '完成' if status == 'SUCCEEDED' else '部分完成', answer,
        [_citation_dict(citation) for citation in citations], len(items),
        '' if status == 'SUCCEEDED' else 'CITATION_VERIFICATION_PARTIAL',
        {**_base_metrics(run, recorder), 'citation_check': verification,
         'findings': len(findings), 'suggested_diffs': len(diffs), 'execution_status': execution,
         'inspected_documents': len(inspected_docs)},
    )


def execute_run(run_id, worker_id='inline'):
    run = AgentRun.objects.select_related('workspace', 'user').filter(run_id=run_id).first()
    if run is None:
        return None
    if run.cancel_requested or run.status == 'CANCELLED':
        _finish(run, 'CANCELLED', '已取消', '任务已取消。', run.citations or [], run.evidence_count, 'CANCELLED_BY_USER')
        return run
    if run.task_type not in TASK_TYPES:
        _finish(run, 'FAILED', '执行失败', '', [], 0, 'UNKNOWN_TASK_TYPE')
        return run
    started = time.monotonic()
    if run.task_type == 'grounded_qa':
        try:
            run_evidence_agent(
                run.user, run.query, domain=run.domain, mode=run.mode, budget=budget_for(run.requested_mode),
                run=run, workspace=run.workspace, cancel_check=lambda: _cancel_requested(run),
            )
        except Exception:
            if run.status not in ('SUCCEEDED', 'COMPLETED', 'ABSTAINED', 'FAILED', 'CANCELLED', 'PARTIAL'):
                _finish(run, 'FAILED', '执行失败', '', [], 0, 'TASK_EXECUTION_ERROR')
        return AgentRun.objects.filter(pk=run.pk).first()

    budget = budget_for(run.requested_mode)
    recorder = StepRecorder(run, budget, cancel_check=lambda: _cancel_requested(run), starting_index=run.steps.count())
    prepared, task_pack, domain_pack = _prepare_skills(run)
    try:
        recorder.record('START', input_summary={'query': run.query, 'task_type': run.task_type, 'workspace': run.workspace_id},
                        decision='BEGIN', reason_code='TASK_ACCEPTED')
        if task_pack is None or domain_pack is None:
            raise BudgetExceeded('TASK_PACK_MISSING')
        recorder.record('ROUTE', output_summary={'domain': domain_pack.pack_id, 'task_pack': task_pack.task_id},
                        decision='ROUTED', reason_code='TASK_PACK_SELECTED')
        recorder.record('PLAN', output_summary={'skills': [skill.skill_id for skill, _loaded, _scope in prepared]},
                        decision='PLANNED', reason_code='TASK_PLAN_READY')
        _record_skill_step(recorder, prepared)
        if run.task_type == 'guided_learning':
            run_guided_learning(run, run.user, recorder, prepared)
        elif run.task_type == 'paper_comparison':
            run_paper_comparison(run, run.user, recorder, prepared)
        elif run.task_type == 'code_investigation':
            run_code_investigation(run, run.user, recorder, prepared)
    except RunCancelled:
        _finish(run, 'CANCELLED', '已取消', '任务已取消，已保留完成步骤与证据。', run.citations or [], run.evidence_count,
                'CANCELLED_BY_USER', _base_metrics(run, recorder))
    except BudgetExceeded as exc:
        _finish(run, 'ABSTAINED', '已拒答', '本次任务超出步骤、Token、工具或延迟预算，系统已停止。',
                [], run.evidence_count, f'BUDGET_EXCEEDED:{exc.code}', _base_metrics(run, recorder))
    except Exception as exc:
        _finish(run, 'FAILED', '执行失败', '', [], run.evidence_count,
                getattr(exc, 'code', type(exc).__name__), {**_base_metrics(run, recorder), 'elapsed_ms': int((time.monotonic() - started) * 1000)})
    return AgentRun.objects.filter(pk=run.pk).first()


def task_budget_dict(mode):
    return asdict(budget_for(mode))
