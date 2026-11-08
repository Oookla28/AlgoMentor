"""Query rewriting for recall only. Rewritten queries are never treated as facts."""

from dataclasses import dataclass, field
import re
import unicodedata

from django.conf import settings

from core.exceptions import BusinessError

_TERM_EXPANSIONS = {
    '队列': '队头 队尾 判空 判满 循环队列 顺序队列',
    '栈': '顺序栈 链栈 入栈 出栈 栈顶 栈底',
    '复杂度': '时间复杂度 空间复杂度 最坏情况 平均情况',
    'kmp': 'next 数组 前缀函数 模式匹配 失配',
    '树': '二叉树 遍历 前序 中序 后序 层序',
    '图': '邻接矩阵 邻接表 深度优先 广度优先 Dijkstra',
    '排序': '快速排序 归并排序 稳定性 时间复杂度',
    '链表': '单链表 双链表 头结点 指针',
    '哈希': '散列表 冲突 装填因子 哈希函数',
    '递归': '递归出口 调用栈 分治',
}
_QUESTION_WORDS = re.compile(r'(什么是|是什么|怎么|如何|为什么|请解释|请说明|请问|介绍一下|的含义|的概念)', re.I)
_PUNCTUATION = re.compile(r'^[\s，。！？；：、,.!?;:]+|[\s，。！？；：、,.!?;:]+$')


@dataclass(frozen=True)
class RewriteResult:
    original: str
    variants: tuple[str, ...]
    used_fallback: bool = True
    fallback_reason: str = ''
    llm_used: bool = False
    route: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            'original': self.original,
            'variants': list(self.variants),
            'used_fallback': self.used_fallback,
            'fallback_reason': self.fallback_reason,
            'llm_used': self.llm_used,
        }


def _normalize(query: str) -> str:
    text = unicodedata.normalize('NFKC', query or '')
    return re.sub(r'\s+', ' ', text).strip()


def _keyword_variant(query: str) -> str:
    stripped = _QUESTION_WORDS.sub(' ', query)
    stripped = re.sub(r'[\s，。！？；：、,.!?;:]+', ' ', stripped).strip()
    if not stripped:
        return ''
    return f'{stripped} 定义 原理 示例'


def _technical_variant(query: str) -> str:
    expansions = []
    lowered = query.lower()
    for term, values in _TERM_EXPANSIONS.items():
        if term in lowered:
            expansions.extend(values.split())
    if not expansions:
        return ''
    return f'{query} {" ".join(dict.fromkeys(expansions))}'


def _intent_variant(query: str, route: dict) -> str:
    extras = []
    if route.get('has_code'):
        extras.extend(['代码', '实现', '调用链', '复杂度'])
    if route.get('has_version'):
        extras.extend(['版本', '差异'])
    if route.get('needs_media'):
        extras.extend(['图片', '视频', '关键帧', '演示'])
    if route.get('possible_conflict'):
        extras.extend(['不同说法', '对比', '适用条件'])
    if not extras:
        return ''
    return f'{query} {" ".join(extras)}'


def heuristic_rewrite(query: str, route: dict | None = None, max_variants: int | None = None) -> RewriteResult:
    from .query_router import route_query
    route = route or route_query(query).to_dict()
    max_variants = max_variants or getattr(settings, 'EVIDENCE_RAG_MAX_QUERY_VARIANTS', 5)
    original = (query or '').strip()
    candidates = [_normalize(original), _keyword_variant(original), _technical_variant(original), _intent_variant(original, route)]
    variants = [original] if original else []
    for candidate in candidates:
        candidate = _PUNCTUATION.sub('', candidate or '').strip()
        if candidate and candidate not in variants:
            variants.append(candidate)
        if len(variants) >= max_variants:
            break
    reason = 'HEURISTIC_FALLBACK' if not getattr(settings, 'EVIDENCE_RAG_QUERY_REWRITE_LLM', False) else ''
    return RewriteResult(original=original, variants=tuple(variants), used_fallback=True, fallback_reason=reason, route=route)


def _llm_variants(query: str, user, max_variants: int) -> tuple[str, ...]:
    from core.llm.deepseek_client import DeepSeekClient
    client = DeepSeekClient(user, purpose='query_rewrite')
    prompt = (
        '你是信息检索查询改写器。只输出 JSON 字符串数组，不要解释。'
        '为下面的课程问题生成 2-4 个用于召回的查询变体，保留原问题含义，不要加入事实结论。'
        f'原问题：{query}'
    )
    result = client.complete([{'role': 'user', 'content': prompt}], max_tokens=300)
    import json
    text = (result.text or '').strip()
    start, end = text.find('['), text.rfind(']')
    if start < 0 or end <= start:
        return ()
    values = json.loads(text[start:end + 1])
    variants = []
    for value in values:
        if isinstance(value, str):
            value = value.strip()
            if value and len(value) <= 500 and value not in variants:
                variants.append(value)
    return tuple(variants[:max(0, max_variants - 1)])


def rewrite_query(query: str, user=None, max_variants: int | None = None, use_llm: bool | None = None) -> RewriteResult:
    """Return the original query first plus recall-oriented variants.

    Any failure (missing key, network, bad JSON) silently degrades to the
    deterministic heuristic result. The original query is never dropped.
    """
    from .query_router import route_query
    original = (query or '').strip()
    route = route_query(original)
    base = heuristic_rewrite(original, route.to_dict(), max_variants)
    if not original:
        return base
    use_llm = getattr(settings, 'EVIDENCE_RAG_QUERY_REWRITE_LLM', False) if use_llm is None else use_llm
    if not use_llm or user is None or not getattr(user, 'is_authenticated', False):
        return base
    try:
        variants = _llm_variants(original, user, max_variants or getattr(settings, 'EVIDENCE_RAG_MAX_QUERY_VARIANTS', 5))
        if variants:
            unique = list(base.variants)
            for variant in variants:
                if variant not in unique:
                    unique.append(variant)
            return RewriteResult(original=original, variants=tuple(unique[:max_variants or 5]), used_fallback=False, fallback_reason='', llm_used=True, route=route.to_dict())
        return RewriteResult(original=original, variants=base.variants, used_fallback=True, fallback_reason='LLM_EMPTY_RESULT', llm_used=False, route=route.to_dict())
    except BusinessError as exc:
        return RewriteResult(original=original, variants=base.variants, used_fallback=True, fallback_reason=exc.code, llm_used=False, route=route.to_dict())
    except Exception:
        return RewriteResult(original=original, variants=base.variants, used_fallback=True, fallback_reason='LLM_REWRITE_FAILED', llm_used=False, route=route.to_dict())
