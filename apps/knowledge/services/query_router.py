"""Lightweight query routing signals. No LLM and no network access."""

from dataclasses import asdict, dataclass
import re

_PRONOUN_RE = re.compile(r'(这|那|它|其|该|上述|上面|刚才|这个|那个|其中)')
_CODE_RE = re.compile(r'(```|`[^`]+`|\bdef\s+\w+|\bclass\s+\w+|\bimport\s+\w+|\bpublic\s+static\b|;\s*$)', re.M)
_VERSION_RE = re.compile(r'(\bv?\d+\.\d+(?:\.\d+)?\b|版本|Python\s*3|JDK\s*\d+)', re.I)
_MEDIA_RE = re.compile(r'(图片|图像|截图|视频|动画|演示|关键帧|ocr|asr)', re.I)
_CONFLICT_RE = re.compile(r'(冲突|矛盾|不一致|不同说法|哪个正确|哪个对|区别是什么|对比|相反)', re.I)


@dataclass(frozen=True)
class QueryRoute:
    query: str
    is_empty: bool
    is_short: bool
    has_pronoun: bool
    has_code: bool
    has_version: bool
    needs_media: bool
    possible_conflict: bool
    needs_rewrite: bool
    suggested_variants: int

    def to_dict(self) -> dict:
        return asdict(self)


def route_query(query: str) -> QueryRoute:
    query = (query or '').strip()
    length = len(query)
    has_pronoun = bool(_PRONOUN_RE.search(query))
    has_code = bool(_CODE_RE.search(query))
    has_version = bool(_VERSION_RE.search(query))
    needs_media = bool(_MEDIA_RE.search(query))
    possible_conflict = bool(_CONFLICT_RE.search(query))
    is_short = 0 < length < 4
    return QueryRoute(
        query=query,
        is_empty=not bool(query),
        is_short=is_short,
        has_pronoun=has_pronoun,
        has_code=has_code,
        has_version=has_version,
        needs_media=needs_media,
        possible_conflict=possible_conflict,
        needs_rewrite=bool(query) and (has_pronoun or is_short or has_code or possible_conflict or length >= 6),
        suggested_variants=1 if is_short else (4 if (has_code or possible_conflict or needs_media) else 3),
    )
