"""Structure-aware recursive character splitting with parent/child chunks.

The primary algorithm is still recursive character splitting. Heading and
section boundaries only decide *where* to prefer a cut and what metadata to
attach; a weak-structure document safely falls back to plain recursive cuts.
"""

from dataclasses import dataclass
import hashlib
import re

from django.conf import settings

from .boundary_detector import detect_protected_ranges, detect_sections, heading_path_at, overlaps_protected
from .document_loader import LoadedDocument

DEFAULT_SEPARATORS = ['\n\n', '\n', '。', '！', '？', '；', '，', '、', ' ', '']
_CJK_RE = re.compile(r'[\u3400-\u4dbf\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]')
_ASCII_WORD_RE = re.compile(r'[A-Za-z0-9_]+')


def estimate_tokens(text: str) -> int:
    """Deterministic token estimate: one CJK character or one Latin word ≈ one token."""
    if not text:
        return 0
    cjk = len(_CJK_RE.findall(text))
    words = len(_ASCII_WORD_RE.findall(text))
    return max(1, cjk + words)


@dataclass(frozen=True)
class HierarchicalChunk:
    chunk_id: str
    parent_chunk_id: str
    chunk_type: str
    content: str
    page_number: int
    heading_path: str
    char_start: int
    char_end: int
    token_count: int
    overlap_start: int
    overlap_end: int
    parser_confidence: float
    content_hash: str
    chapter: str
    section: str


@dataclass(frozen=True)
class ChunkingResult:
    parents: tuple[HierarchicalChunk, ...]
    children: tuple[HierarchicalChunk, ...]
    text: str
    page_ranges: tuple[tuple[int, int, int], ...]
    structure_confidence: float
    has_headings: bool

    @property
    def all_chunks(self):
        return self.parents + self.children


@dataclass(frozen=True)
class _Segment:
    start: int
    end: int
    protected: bool


def _find_cut_positions(text: str, start: int, end: int, separator: str, protected) -> list[int]:
    positions = []
    offset = start
    while True:
        found = text.find(separator, offset, end)
        if found < 0:
            break
        cut = found + len(separator)
        if not overlaps_protected(found, cut, protected):
            positions.append(cut)
        offset = max(cut, found + 1)
    return positions


def _recursive_segments(text: str, start: int, end: int, max_tokens: int, separators, protected, depth=0) -> list[_Segment]:
    if end <= start:
        return []
    if estimate_tokens(text[start:end]) <= max_tokens:
        return [_Segment(start, end, overlaps_protected(start, end, protected))]
    if overlaps_protected(start, end, protected):
        # Code fences, tables and display formulas stay atomic even when oversized.
        return [_Segment(start, end, True)]
    if depth >= 12 or not separators:
        return _hard_split(text, start, end, max_tokens, protected)
    for index, separator in enumerate(separators):
        if separator == '':
            break
        cuts = _find_cut_positions(text, start, end, separator, protected)
        if not cuts:
            continue
        pieces = []
        cursor = start
        for cut in cuts:
            if cut <= cursor:
                continue
            pieces.extend(_recursive_segments(text, cursor, cut, max_tokens, separators[index + 1:], protected, depth + 1))
            cursor = cut
        if cursor < end:
            pieces.extend(_recursive_segments(text, cursor, end, max_tokens, separators[index + 1:], protected, depth + 1))
        if pieces:
            return pieces
    return _hard_split(text, start, end, max_tokens, protected)


def _hard_split(text: str, start: int, end: int, max_tokens: int, protected) -> list[_Segment]:
    segments = []
    cursor = start
    while cursor < end:
        # Advance until the estimated budget is reached, never cutting inside a protected block.
        low, high, best = cursor + 1, end, cursor + 1
        while low <= high:
            middle = (low + high) // 2
            if estimate_tokens(text[cursor:middle]) <= max_tokens:
                best = middle
                low = middle + 1
            else:
                high = middle - 1
        cut = max(best, cursor + 1)
        for range_start, range_end in protected:
            if range_start < cut < range_end:
                cut = range_end
                break
        cut = min(cut, end)
        segments.append(_Segment(cursor, cut, overlaps_protected(cursor, cut, protected)))
        cursor = cut
    return segments


def _pack_spans(text: str, segments: list[_Segment], max_tokens: int) -> list[tuple[int, int]]:
    spans = []
    current_start = None
    current_end = None
    current_tokens = 0
    for segment in segments:
        segment_tokens = estimate_tokens(text[segment.start:segment.end])
        if current_start is not None and current_tokens + segment_tokens > max_tokens:
            spans.append((current_start, current_end))
            current_start = None
            current_tokens = 0
        if current_start is None:
            current_start, current_end = segment.start, segment.end
        else:
            current_end = segment.end
        current_tokens += segment_tokens
    if current_start is not None:
        spans.append((current_start, current_end))
    return spans


def _merge_short_spans(text: str, spans: list[tuple[int, int]], min_tokens: int, max_tokens: int):
    merged: list[tuple[int, int]] = []
    for start, end in spans:
        tokens = estimate_tokens(text[start:end])
        if merged:
            previous_tokens = estimate_tokens(text[merged[-1][0]:merged[-1][1]])
            if (previous_tokens < min_tokens or tokens < min_tokens) and previous_tokens + tokens <= max_tokens:
                merged[-1] = (merged[-1][0], end)
                continue
        merged.append((start, end))
    return merged


def _apply_overlap(text: str, spans: list[tuple[int, int]], overlap_tokens: int, protected, parent_start: int):
    if not spans:
        return []
    adjusted = [list(spans[0])]
    for start, end in spans[1:]:
        previous_start, previous_end = adjusted[-1]
        desired = max(previous_end - overlap_tokens, parent_start)
        half_previous = previous_start + max(1, (previous_end - previous_start) // 2)
        desired = max(desired, half_previous)
        if desired >= start or overlaps_protected(desired, start, protected):
            desired = start
        adjusted.append([desired, end])
    return [(start, end) for start, end in adjusted]


def _page_for(offset: int, page_ranges) -> int:
    for start, end, number in page_ranges:
        if start <= offset < end or (offset == end and end == page_ranges[-1][1]):
            return number
    return page_ranges[-1][2] if page_ranges else 1


def _chapter_section(heading_path: str) -> tuple[str, str]:
    if not heading_path:
        return '课程知识库', '概念与示例'
    parts = [item.strip() for item in heading_path.split('>') if item.strip()]
    return parts[0][:100], (parts[-1] if parts else '概念与示例')[:150]


def _chunk(prefix: str, index: int, chunk_type: str, parent_id: str, text: str, start: int, end: int,
           heading_path: str, page_ranges, confidence: float, overlap_start: int = 0, overlap_end: int = 0) -> HierarchicalChunk:
    content = text[start:end]
    chapter, section = _chapter_section(heading_path)
    chunk_id = f'{prefix}-{chunk_type[0].upper()}{index:03d}' if chunk_type == 'parent' else f'{prefix}-{parent_id.rsplit("-", 1)[-1]}-C{index:02d}'
    return HierarchicalChunk(
        chunk_id=chunk_id,
        parent_chunk_id=parent_id,
        chunk_type=chunk_type,
        content=content,
        page_number=_page_for(start, page_ranges),
        heading_path=heading_path,
        char_start=start,
        char_end=end,
        token_count=estimate_tokens(content),
        overlap_start=overlap_start,
        overlap_end=overlap_end,
        parser_confidence=confidence,
        content_hash=hashlib.sha256(content.encode('utf-8')).hexdigest(),
        chapter=chapter,
        section=section,
    )


def chunk_document(document: LoadedDocument, parent_token_min=None, parent_token_max=None,
                   child_token_min=None, child_token_max=None, overlap_ratio=None) -> ChunkingResult:
    parent_token_min = parent_token_min or getattr(settings, 'EVIDENCE_RAG_PARENT_TOKEN_MIN', 1200)
    parent_token_max = parent_token_max or getattr(settings, 'EVIDENCE_RAG_PARENT_TOKEN_MAX', 2000)
    child_token_min = child_token_min or getattr(settings, 'EVIDENCE_RAG_CHILD_TOKEN_MIN', 300)
    child_token_max = child_token_max or getattr(settings, 'EVIDENCE_RAG_CHILD_TOKEN_MAX', 500)
    overlap_ratio = getattr(settings, 'EVIDENCE_RAG_CHILD_OVERLAP_RATIO', 0.12) if overlap_ratio is None else overlap_ratio

    parts = []
    cursor = 0
    page_ranges = []
    for index, page in enumerate(document.pages):
        if index:
            parts.append('\n\n')
            cursor += 2
        start = cursor
        parts.append(page.text)
        cursor += len(page.text)
        page_ranges.append((start, cursor, page.page_number))
    text = ''.join(parts)
    if not text.strip():
        return ChunkingResult((), (), text, tuple(page_ranges), 0.0, False)

    boundary = detect_sections(text)
    protected = detect_protected_ranges(text)
    parent_spans: list[tuple[int, int]] = []
    current_start = None
    current_end = None
    current_tokens = 0
    for section in boundary.sections:
        if not text[section.start:section.end].strip():
            continue
        section_tokens = estimate_tokens(text[section.start:section.end])
        if section_tokens > parent_token_max:
            if current_start is not None:
                parent_spans.append((current_start, current_end))
                current_start = None
                current_tokens = 0
            segments = _recursive_segments(text, section.start, section.end, parent_token_max, DEFAULT_SEPARATORS, protected)
            for segment in segments:
                parent_spans.append((segment.start, segment.end))
            continue
        if current_start is None:
            current_start, current_end, current_tokens = section.start, section.end, section_tokens
        elif current_tokens + section_tokens <= parent_token_max:
            current_end = section.end
            current_tokens += section_tokens
        else:
            parent_spans.append((current_start, current_end))
            current_start, current_end, current_tokens = section.start, section.end, section_tokens
    if current_start is not None:
        parent_spans.append((current_start, current_end))

    # Merge a short tail/head when the combined parent still respects the max budget.
    merged: list[tuple[int, int]] = []
    for start, end in parent_spans:
        if merged:
            previous_tokens = estimate_tokens(text[merged[-1][0]:merged[-1][1]])
            this_tokens = estimate_tokens(text[start:end])
            if previous_tokens < parent_token_min and previous_tokens + this_tokens <= parent_token_max:
                merged[-1] = (merged[-1][0], end)
                continue
        merged.append((start, end))
    parent_spans = merged

    prefix = f'adv-{document.document_hash[:12]}'
    parents = []
    children = []
    overlap_tokens = max(1, int(child_token_max * overlap_ratio))
    for parent_index, (start, end) in enumerate(parent_spans, 1):
        heading = heading_path_at(text, start)
        confidence = boundary.confidence if heading else max(0.25, boundary.confidence * 0.8)
        parent = _chunk(prefix, parent_index, 'parent', '', text, start, end, heading, page_ranges, confidence)
        parents.append(parent)
        segments = _recursive_segments(text, start, end, child_token_max, DEFAULT_SEPARATORS, protected)
        pack_max = max(child_token_min, child_token_max - overlap_tokens)
        spans = _pack_spans(text, segments, pack_max)
        spans = _merge_short_spans(text, spans, child_token_min, child_token_max)
        spans = _apply_overlap(text, spans, overlap_tokens, protected, start)
        for child_index, (child_start, child_end) in enumerate(spans, 1):
            overlap_start = max(0, spans[child_index - 2][1] - child_start) if child_index > 1 else 0
            overlap_end = max(0, child_end - spans[child_index][0]) if child_index < len(spans) else 0
            child_heading = heading_path_at(text, child_start) or heading
            children.append(_chunk(prefix, child_index, 'child', parent.chunk_id, text, child_start, child_end,
                                   child_heading, page_ranges, confidence, overlap_start, overlap_end))
    return ChunkingResult(tuple(parents), tuple(children), text, tuple(page_ranges), boundary.confidence, boundary.has_headings)


def structure_aware_recursive_split(document: LoadedDocument, **kwargs) -> ChunkingResult:
    """Named entry point for the Structure-aware Recursive Character Splitting method."""
    return chunk_document(document, **kwargs)


def split_notes(text: str, name: str = 'notes.txt', document_hash: str = '') -> ChunkingResult:
    """Convenience wrapper for tests and for text that did not come from a file."""
    from pathlib import Path
    from .document_loader import SourcePage
    digest = document_hash or hashlib.sha256((name + '\n' + text).encode('utf-8')).hexdigest()
    document = LoadedDocument(Path(name), name, digest, (SourcePage(1, text),))
    return chunk_document(document)
