"""Detect structural boundaries for structure-aware recursive splitting.

Headings are used for boundary priority and metadata only. When the document
has no reliable structure the caller falls back to plain recursive character
splitting and keeps a low ``parser_confidence`` value.
"""

from dataclasses import dataclass
import re


CHAPTER_RE = re.compile(r'^第[一二三四五六七八九十百零〇\d]{1,4}章[^\n]{0,50}$', re.M)
MARKDOWN_RE = re.compile(r'^(#{1,6})[ \t]+(\S[^\n]{0,80})$', re.M)
NUMBERED_RE = re.compile(r'^(\d{1,2}(?:\.\d{1,2}){0,3})[、.．]?[ \t]+(\S[^\n]{0,60})$', re.M)
CN_HEADING_RE = re.compile(r'^([一二三四五六七八九十]{1,3})[、.．][ \t]*(\S[^\n]{0,50})$', re.M)


@dataclass(frozen=True)
class Section:
    start: int
    end: int
    level: int
    title: str
    kind: str
    heading_path: str


@dataclass(frozen=True)
class BoundaryResult:
    sections: tuple[Section, ...]
    confidence: float
    has_headings: bool
    headings: tuple[tuple[int, int, str], ...]

    @property
    def weak_structure(self) -> bool:
        return self.confidence < 0.45


def _heading_candidates(text: str):
    candidates = []
    for match in MARKDOWN_RE.finditer(text):
        title = match.group(2).strip()
        if title and not title.endswith(('。', '；', '，', '！', '？')):
            candidates.append((match.start(), len(match.group(1)), title, 'markdown'))
    for match in CHAPTER_RE.finditer(text):
        title = match.group(0).strip()
        candidates.append((match.start(), 1, title, 'chapter'))
    for match in NUMBERED_RE.finditer(text):
        title = match.group(0).strip()
        if title.endswith(('。', '；', '，', '！', '？')):
            continue
        level = min(4, match.group(1).count('.') + 2)
        candidates.append((match.start(), level, title, 'numbered'))
    for match in CN_HEADING_RE.finditer(text):
        title = match.group(0).strip()
        if title.endswith(('。', '；', '，', '！', '？')):
            continue
        candidates.append((match.start(), 2, title, 'chinese'))
    # Deduplicate overlapping candidates, preferring the earliest and shallowest.
    candidates.sort(key=lambda item: (item[0], item[1]))
    unique = []
    for item in candidates:
        if unique and item[0] - unique[-1][0] < 2:
            continue
        unique.append(item)
    return unique


def _line_end(text: str, offset: int) -> int:
    newline = text.find('\n', offset)
    return len(text) if newline == -1 else newline + 1


def detect_sections(text: str) -> BoundaryResult:
    text = text or ''
    candidates = _heading_candidates(text)
    if not candidates:
        body = Section(0, len(text), 1, '', 'body', '')
        return BoundaryResult((body,), 0.25, False, ())

    headings = tuple((start, level, title) for start, level, title, _kind in candidates)
    sections = []
    if candidates[0][0] > 0 and text[:candidates[0][0]].strip():
        sections.append(Section(0, candidates[0][0], 1, '', 'preamble', ''))
    stack: list[tuple[int, str]] = []
    for index, (start, level, title, kind) in enumerate(candidates):
        while stack and stack[-1][0] >= level:
            stack.pop()
        stack.append((level, title))
        path = ' > '.join(item[1] for item in stack)
        end = candidates[index + 1][0] if index + 1 < len(candidates) else len(text)
        # The heading line itself belongs to this section.
        end = max(_line_end(text, start), end)
        if end <= start:
            end = len(text)
        sections.append(Section(start, min(end, len(text)), level, title, kind, path))
    confidence = 0.9 if len(candidates) >= 2 else 0.75
    return BoundaryResult(tuple(sections), confidence, True, headings)


def heading_path_at(text: str, offset: int) -> str:
    candidates = _heading_candidates(text)
    path = ''
    stack: list[tuple[int, str]] = []
    for start, level, title, _kind in candidates:
        if start > offset:
            break
        while stack and stack[-1][0] >= level:
            stack.pop()
        stack.append((level, title))
        path = ' > '.join(item[1] for item in stack)
    return path


_CODE_FENCE_RE = re.compile(r'(?ms)^(`{3,}|~{3,})[^\n]*\n.*?^\1[ \t]*$')
_MATH_BLOCK_RE = re.compile(r'(?ms)\$\$.*?\$\$|\\\[.*?\\\]')
_TABLE_BLOCK_RE = re.compile(r'(?m)(?:^\|?[^\n]*\|[^\n]*\n){2,}')


def detect_protected_ranges(text: str) -> tuple[tuple[int, int], ...]:
    """Ranges that must not be cut by the recursive splitter: code, tables, display math."""
    ranges: list[tuple[int, int]] = []
    for pattern in (_CODE_FENCE_RE, _MATH_BLOCK_RE, _TABLE_BLOCK_RE):
        for match in pattern.finditer(text or ''):
            start, end = match.span()
            if end - start >= 2:
                ranges.append((start, end))
    ranges.sort()
    merged: list[tuple[int, int]] = []
    for start, end in ranges:
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return tuple(merged)


def overlaps_protected(start: int, end: int, ranges: tuple[tuple[int, int], ...]) -> bool:
    return any(start < range_end and end > range_start for range_start, range_end in ranges)
