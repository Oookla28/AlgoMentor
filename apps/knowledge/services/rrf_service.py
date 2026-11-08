"""Reciprocal Rank Fusion (RRF) with per-route provenance.

RRF(d) = sum_i 1 / (k + rank_i(d)), rank starting at 1. Ties are broken by
best single-route rank and then chunk_id for deterministic output.
"""

from dataclasses import dataclass, field

from django.conf import settings

from core.exceptions import ValidationError


@dataclass(frozen=True)
class RRFEntry:
    chunk_id: str
    score: float
    ranks: tuple[tuple[str, int], ...] = field(default_factory=tuple)
    best_rank: int = 0


def reciprocal_rank_fusion(rankings, k: int | None = None) -> list[RRFEntry]:
    """Fuse ranked chunk-id lists.

    ``rankings`` may be a list of lists (route names are positional) or a
    mapping route_name -> list. Duplicates inside one route are ignored after
    their first occurrence; chunk ids are deduplicated across routes.
    """
    if k is None:
        k = getattr(settings, 'EVIDENCE_RAG_RRF_K', 60)
    k = max(1, int(k))
    if isinstance(rankings, dict):
        routes = list(rankings.items())
    else:
        routes = [(f'route_{index}', ranking) for index, ranking in enumerate(rankings)]
    scores: dict[str, float] = {}
    provenance: dict[str, list[tuple[str, int]]] = {}
    for route_name, ranking in routes:
        if ranking is None:
            continue
        if isinstance(ranking, (str, bytes)) or not hasattr(ranking, '__iter__'):
            raise ValidationError('RRF 输入必须是排序后的片段编号列表。', code='RRF_INVALID_INPUT')
        seen = set()
        rank = 0
        for item in ranking:
            chunk_id = getattr(item, 'chunk_id', item)
            if not isinstance(chunk_id, str) or not chunk_id:
                continue
            if chunk_id in seen:
                continue
            seen.add(chunk_id)
            rank += 1
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (k + rank)
            provenance.setdefault(chunk_id, []).append((route_name, rank))
    entries = [
        RRFEntry(
            chunk_id=chunk_id,
            score=round(score, 8),
            ranks=tuple(provenance[chunk_id]),
            best_rank=min(rank for _name, rank in provenance[chunk_id]),
        )
        for chunk_id, score in scores.items()
    ]
    entries.sort(key=lambda entry: (-entry.score, entry.best_rank, entry.chunk_id))
    return entries
