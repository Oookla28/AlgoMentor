"""Small2Big: retrieve a small child chunk, return its parent and siblings as context."""

from dataclasses import replace

from django.conf import settings

from .hierarchical_chunker import estimate_tokens


def _trim_to_tokens(text: str, budget: int) -> tuple[str, bool]:
    if estimate_tokens(text) <= budget:
        return text, False
    if budget <= 0:
        return '', True
    low, high, best = 0, len(text), 0
    while low <= high:
        middle = (low + high) // 2
        if estimate_tokens(text[:middle]) <= budget:
            best = middle
            low = middle + 1
        else:
            high = middle - 1
    return text[:max(1, best)] + '…', True


def build_context(chunk, budget_tokens: int | None = None) -> dict:
    """Return parent context, hit child and adjacent siblings within a token budget.

    The original hit is always represented first; an oversized parent is
    truncated around the child instead of dropping the evidence entirely.
    """
    budget_tokens = budget_tokens if budget_tokens is not None else getattr(settings, 'EVIDENCE_RAG_CONTEXT_TOKEN_BUDGET', 1800)
    parent = chunk.parent_chunk if chunk.parent_chunk_id else None
    parts = []
    used = 0
    truncated = False
    if parent is not None:
        heading = parent.heading_path or chunk.heading_path
        header = f'【父块 {parent.chunk_id}】' + (f' {heading}' if heading else '')
        parts.append(header)
        used += estimate_tokens(header)
        hit_budget = min(estimate_tokens(chunk.content), max(60, budget_tokens // 4))
        parent_budget = max(0, budget_tokens - used - hit_budget)
        parent_text, cut = _trim_to_tokens(parent.content, parent_budget)
        parts.append(parent_text)
        used += estimate_tokens(parent_text)
        truncated = truncated or cut
        hit_text, hit_cut = _trim_to_tokens(chunk.content, hit_budget)
        parts.append(f'【命中子块 {chunk.chunk_id}】\n{hit_text}')
        used += estimate_tokens(hit_text)
        truncated = truncated or hit_cut
        siblings = list(parent.children.filter(is_active=True).exclude(pk=chunk.pk).order_by('chunk_id')[:4])
        for sibling in siblings:
            if used >= budget_tokens:
                truncated = True
                break
            sibling_text, cut = _trim_to_tokens(sibling.content, max(0, budget_tokens - used))
            parts.append(f'【相邻片段 {sibling.chunk_id}】\n{sibling_text}')
            used += estimate_tokens(sibling_text)
            truncated = truncated or cut
    else:
        text, cut = _trim_to_tokens(chunk.content, budget_tokens)
        parts.append(text)
        used = estimate_tokens(text)
        truncated = cut
    context = '\n\n'.join(part for part in parts if part)
    return {
        'context': context,
        'matched_content': chunk.content,
        'parent_chunk_id': parent.chunk_id if parent else '',
        'heading_path': chunk.heading_path or (parent.heading_path if parent else ''),
        'token_count': used,
        'truncated': truncated,
        'page_number': chunk.page_number,
        'char_start': chunk.char_start,
        'char_end': chunk.char_end,
    }


def expand_citations(citations, budget_tokens: int | None = None):
    """Replace advanced citations with Small2Big context while keeping every original field."""
    from apps.knowledge.models import KnowledgeChunk
    if not citations:
        return citations
    budget = budget_tokens if budget_tokens is not None else getattr(settings, 'EVIDENCE_RAG_CONTEXT_TOKEN_BUDGET', 1800)
    remaining = budget
    expanded = []
    chunk_ids = [citation.chunk_id for citation in citations if not citation.chunk_id.startswith(('correction-', 'media:'))]
    rows = {
        row.chunk_id: row
        for row in KnowledgeChunk.objects.select_related('parent_chunk', 'document', 'media_asset').filter(chunk_id__in=chunk_ids)
    }
    for citation in citations:
        row = rows.get(citation.chunk_id)
        if row is None:
            expanded.append(citation)
            continue
        allocation = max(120, min(remaining, budget // max(1, len(citations))))
        window = build_context(row, allocation)
        remaining = max(0, remaining - window['token_count'])
        expanded.append(replace(
            citation,
            content=citation.content,
            matched_content=window['matched_content'],
            context=window['context'],
            parent_chunk_id=window['parent_chunk_id'],
            heading_path=window['heading_path'],
            chunk_type=row.chunk_type,
            char_start=window['char_start'],
            char_end=window['char_end'],
            evidence_id=f'chunk:{row.chunk_id}',
            media_asset_id=row.media_asset.asset_id if row.media_asset_id else '',
            start_time=row.media_asset.start_time if row.media_asset_id else None,
            end_time=row.media_asset.end_time if row.media_asset_id else None,
            authority_level=row.document.authority_level,
            source_uri=f'/knowledge/source/{row.chunk_id}/',
        ))
    return expanded
