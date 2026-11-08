"""Deterministic reranking with an optional cross-encoder backend.

The deterministic scorer always works offline. A cross-encoder is loaded only
when explicitly configured and available; any failure falls back and records
the reason without breaking retrieval.
"""

from dataclasses import dataclass
import math

from django.conf import settings
from django.utils import timezone

from .sparse_retrieval import tokenize


@dataclass(frozen=True)
class RerankCandidate:
    chunk_id: str
    content: str
    heading_path: str = ''
    authority_level: int = 3
    parser_confidence: float = 1.0
    freshness: float = 0.7
    rrf_score: float = 0.0
    raw_score: float = 0.0
    rerank_score: float = 0.0

    def with_score(self, score: float):
        return RerankCandidate(**{**self.__dict__, 'rerank_score': round(max(0.0, min(1.0, score)), 6)})


def freshness_score(valid_from=None, valid_to=None, created_at=None) -> float:
    now = timezone.now()
    if valid_to is not None and now > valid_to:
        return 0.1
    if valid_from is not None and now < valid_from:
        return 0.3
    if created_at is not None:
        age_days = max(0.0, (now - created_at).total_seconds() / 86400)
        return round(max(0.35, 1.0 - age_days / 3650), 4)
    return 0.7


def _ratio(tokens, reference) -> float:
    if not reference:
        return 0.0
    return len(tokens & reference) / len(reference)


def _jaccard(left, right) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def deterministic_rerank(query: str, candidates, weights=None) -> list[RerankCandidate]:
    query_tokens = set(tokenize(query))
    candidates = [candidate if isinstance(candidate, RerankCandidate) else RerankCandidate(**candidate) for candidate in candidates]
    if not candidates:
        return []
    weights = weights or {
        'rrf': 0.42, 'overlap': 0.20, 'heading': 0.10, 'authority': 0.08,
        'parser': 0.07, 'freshness': 0.05, 'raw': 0.08, 'redundancy': 0.15,
    }
    largest_rrf = max((candidate.rrf_score for candidate in candidates), default=0.0) or 1.0
    largest_raw = max((candidate.raw_score for candidate in candidates), default=0.0) or 1.0
    enriched = []
    content_tokens = {}
    for candidate in candidates:
        tokens = set(tokenize(candidate.content))
        content_tokens[candidate.chunk_id] = tokens
        heading_tokens = set(tokenize(candidate.heading_path))
        base = (
            weights['rrf'] * (candidate.rrf_score / largest_rrf)
            + weights['overlap'] * _ratio(query_tokens, tokens)
            + weights['heading'] * _ratio(query_tokens, heading_tokens)
            + weights['authority'] * max(0.0, min(1.0, 1 - (candidate.authority_level - 1) / 4))
            + weights['parser'] * max(0.0, min(1.0, candidate.parser_confidence))
            + weights['freshness'] * max(0.0, min(1.0, candidate.freshness))
            + weights['raw'] * (candidate.raw_score / largest_raw)
        )
        enriched.append((candidate, base))
    selected: list[RerankCandidate] = []
    pool = list(enriched)
    while pool:
        best_index = 0
        best_score = -math.inf
        for index, (candidate, base) in enumerate(pool):
            redundancy = 0.0
            for chosen in selected:
                redundancy = max(redundancy, _jaccard(content_tokens[candidate.chunk_id], content_tokens[chosen.chunk_id]))
            score = base - weights['redundancy'] * redundancy
            if score > best_score:
                best_score, best_index = score, index
        candidate, _base = pool.pop(best_index)
        selected.append(candidate.with_score(best_score))
    return selected


def cross_encoder_rerank(query: str, candidates) -> list[RerankCandidate]:
    from sentence_transformers import CrossEncoder
    model = CrossEncoder(
        getattr(settings, 'EVIDENCE_RAG_CROSS_ENCODER_MODEL', 'BAAI/bge-reranker-base'),
        local_files_only=getattr(settings, 'LOCAL_EMBEDDING_OFFLINE_MODE', True),
    )
    pairs = [(query, candidate.content) for candidate in candidates]
    scores = model.predict(pairs)
    if hasattr(scores, 'tolist'):
        scores = scores.tolist()
    values = [float(value) for value in scores]
    low, high = min(values), max(values)
    normalized = [0.5 if high == low else (value - low) / (high - low) for value in values]
    ordered = [candidate.with_score(score) for candidate, score in zip(candidates, normalized)]
    ordered.sort(key=lambda candidate: (-candidate.rerank_score, candidate.chunk_id))
    return ordered


def rerank(query: str, candidates, backend: str | None = None) -> tuple[list[RerankCandidate], str, str]:
    """Return (ordered candidates, backend used, fallback reason)."""
    backend = backend or getattr(settings, 'EVIDENCE_RAG_RERANK_BACKEND', 'deterministic')
    prepared = [candidate if isinstance(candidate, RerankCandidate) else RerankCandidate(**candidate) for candidate in candidates]
    if backend == 'cross_encoder':
        try:
            return cross_encoder_rerank(query, prepared), 'cross_encoder', ''
        except Exception:
            return deterministic_rerank(query, prepared), 'deterministic', 'CROSS_ENCODER_UNAVAILABLE'
    return deterministic_rerank(query, prepared), 'deterministic', ''
