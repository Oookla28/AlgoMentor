"""Lightweight conflict detection and evidence arbitration.

Only rule-based signals are required: negation, numbers, units, versions,
time ranges and high-similarity/opposite-stance pairs. An NLI or LLM backend
can be plugged in later; the deterministic path never calls the network.
"""

from dataclasses import dataclass, field
import hashlib
import re

from django.conf import settings

from .sparse_retrieval import tokenize

_NEGATION_RE = re.compile(r'(不|非|无|未|不能|不会|禁止|没有|并非|不是)')
_NUMBER_RE = re.compile(r'-?\d+(?:\.\d+)?')
_VERSION_RE = re.compile(r'v?\d+\.\d+(?:\.\d+)?', re.I)
_UNIT_RE = re.compile(r'(\d+)\s*(个|次|层|位|种|字节|比特|位)')
_YEAR_RE = re.compile(r'(\d{4})\s*年')


@dataclass(frozen=True)
class ConflictSignal:
    conflict_type: str
    confidence: float


@dataclass(frozen=True)
class DetectedConflict:
    claim_a_id: str
    claim_b_id: str
    conflict_type: str
    confidence: float
    verdict: str
    authority_scores: dict = field(default_factory=dict)
    freshness_scores: dict = field(default_factory=dict)
    explanation: str = ''

    @property
    def conflict_id(self) -> str:
        first, second = sorted((self.claim_a_id, self.claim_b_id))
        return hashlib.sha256(f'{first}|{second}|{self.conflict_type}'.encode('utf-8')).hexdigest()[:32]


def _tokens(text: str) -> set[str]:
    return set(tokenize(text))


def _negated(text: str) -> bool:
    return bool(_NEGATION_RE.search(text))


def classify_pair(text_a: str, text_b: str, threshold: float | None = None) -> ConflictSignal | None:
    threshold = threshold if threshold is not None else getattr(settings, 'EVIDENCE_RAG_CONFLICT_SIMILARITY', 0.55)
    tokens_a, tokens_b = _tokens(text_a), _tokens(text_b)
    if not tokens_a or not tokens_b:
        return None
    similarity = len(tokens_a & tokens_b) / len(tokens_a | tokens_b)
    if similarity < threshold:
        return None
    if text_a.strip() == text_b.strip():
        return None
    if _negated(text_a) != _negated(text_b):
        return ConflictSignal('NEGATION', round(similarity, 4))
    years_a, years_b = set(_YEAR_RE.findall(text_a)), set(_YEAR_RE.findall(text_b))
    if (years_a or years_b) and years_a != years_b:
        return ConflictSignal('TEMPORAL', round(similarity, 4))
    versions_a, versions_b = set(_VERSION_RE.findall(text_a)), set(_VERSION_RE.findall(text_b))
    if (versions_a or versions_b) and versions_a != versions_b:
        return ConflictSignal('VERSION', round(similarity, 4))
    units_a, units_b = set(_UNIT_RE.findall(text_a)), set(_UNIT_RE.findall(text_b))
    if units_a and units_b and units_a != units_b:
        return ConflictSignal('UNIT', round(similarity, 4))
    numbers_a, numbers_b = set(_NUMBER_RE.findall(text_a)), set(_NUMBER_RE.findall(text_b))
    if (numbers_a or numbers_b) and numbers_a != numbers_b:
        return ConflictSignal('NUMERIC', round(similarity, 4))
    return ConflictSignal('STANCE', round(similarity, 4))


def _freshness(claim) -> float:
    from .rerank_service import freshness_score
    return freshness_score(claim.valid_from, claim.valid_to, getattr(claim, 'created_at', None))


def _explanation(claim_a, claim_b, signal: ConflictSignal, score_a: float, score_b: float, gap: float) -> str:
    source_a = getattr(getattr(claim_a, 'source_chunk', None), 'chunk_id', '')
    source_b = getattr(getattr(claim_b, 'source_chunk', None), 'chunk_id', '')
    if abs(score_a - score_b) < gap:
        verdict = '当前证据的权威性与时效性差距不足，暂不能确定哪一条正确。'
    elif score_a > score_b:
        verdict = '证据 A 的权威性与时效性综合更高，但原文差异仍需人工复核。'
    else:
        verdict = '证据 B 的权威性与时效性综合更高，但原文差异仍需人工复核。'
    return (
        f'检测到 {signal.conflict_type} 冲突（相似度 {signal.confidence:.2f}）。'
        f'A={source_a}（权威分 {score_a:.2f}）；B={source_b}（权威分 {score_b:.2f}）。{verdict}'
    )


def detect_conflicts(claims, similarity_threshold=None, score_gap=None, retrieval_scores=None, backend=None) -> list[DetectedConflict]:
    """Detect conflicts with rule signals, optionally delegating to an NLI/LLM backend.

    ``backend(claim_a, claim_b)`` may return a ``ConflictSignal`` or None. It is
    only consulted for pairs that already pass the lexical similarity gate.
    """
    threshold = similarity_threshold if similarity_threshold is not None else getattr(settings, 'EVIDENCE_RAG_CONFLICT_SIMILARITY', 0.55)
    gap = score_gap if score_gap is not None else getattr(settings, 'EVIDENCE_RAG_CONFLICT_SCORE_GAP', 0.12)
    retrieval_scores = retrieval_scores or {}
    results = []
    seen = set()
    claims = list(claims)
    for index, claim_a in enumerate(claims):
        for claim_b in claims[index + 1:]:
            if getattr(claim_a, 'source_chunk_id', None) and claim_a.source_chunk_id == claim_b.source_chunk_id:
                continue
            pair_key = tuple(sorted((claim_a.claim_id, claim_b.claim_id)))
            if pair_key in seen:
                continue
            subject_a = (getattr(claim_a, 'subject', '') or '').strip()
            subject_b = (getattr(claim_b, 'subject', '') or '').strip()
            if subject_a and subject_b:
                subject_terms_a, subject_terms_b = _tokens(subject_a), _tokens(subject_b)
                if not subject_terms_a or not subject_terms_b:
                    continue
                subject_similarity = len(subject_terms_a & subject_terms_b) / len(subject_terms_a | subject_terms_b)
                if subject_similarity < 0.60:
                    continue
            signal = classify_pair(claim_a.normalized_text, claim_b.normalized_text, threshold)
            if signal is None and backend is not None:
                try:
                    signal = backend(claim_a, claim_b)
                except Exception:
                    signal = None
            if signal is None:
                continue
            seen.add(pair_key)
            freshness_a, freshness_b = _freshness(claim_a), _freshness(claim_b)
            authority_a = max(0.0, min(1.0, 1 - (claim_a.authority_level - 1) / 4))
            authority_b = max(0.0, min(1.0, 1 - (claim_b.authority_level - 1) / 4))
            chunk_a = getattr(claim_a.source_chunk, 'chunk_id', '')
            chunk_b = getattr(claim_b.source_chunk, 'chunk_id', '')
            retrieval_a = float(retrieval_scores.get(chunk_a, 0.5))
            retrieval_b = float(retrieval_scores.get(chunk_b, 0.5))
            composite_a = 0.4 * authority_a + 0.25 * freshness_a + 0.15 * claim_a.detector_score + 0.2 * retrieval_a
            composite_b = 0.4 * authority_b + 0.25 * freshness_b + 0.15 * claim_b.detector_score + 0.2 * retrieval_b
            if abs(composite_a - composite_b) < gap:
                verdict = 'UNRESOLVED'
            elif composite_a > composite_b:
                verdict = 'A_WINS'
            else:
                verdict = 'B_WINS'
            results.append(DetectedConflict(
                claim_a_id=claim_a.claim_id,
                claim_b_id=claim_b.claim_id,
                conflict_type=signal.conflict_type,
                confidence=signal.confidence,
                verdict=verdict,
                authority_scores={'a': round(authority_a, 4), 'b': round(authority_b, 4)},
                freshness_scores={'a': round(freshness_a, 4), 'b': round(freshness_b, 4)},
                explanation=_explanation(claim_a, claim_b, signal, composite_a, composite_b, gap),
            ))
    return results


def detect_and_store_conflicts(trace, claims, retrieval_scores=None, backend=None) -> list:
    from apps.knowledge.models import KnowledgeConflict
    claim_map = {claim.claim_id: claim for claim in claims}
    stored = []
    for detected in detect_conflicts(claims, retrieval_scores=retrieval_scores, backend=backend):
        claim_a = claim_map.get(detected.claim_a_id)
        claim_b = claim_map.get(detected.claim_b_id)
        if claim_a is None or claim_b is None or not getattr(claim_a, 'pk', None) or not getattr(claim_b, 'pk', None):
            continue
        row, _created = KnowledgeConflict.objects.update_or_create(
            conflict_id=detected.conflict_id,
            defaults={
                'query_trace': trace,
                'claim_a': claim_a,
                'claim_b': claim_b,
                'conflict_type': detected.conflict_type,
                'confidence': detected.confidence,
                'authority_scores': detected.authority_scores,
                'freshness_scores': detected.freshness_scores,
                'verdict': detected.verdict,
                'explanation': detected.explanation,
            },
        )
        stored.append(row)
    return stored


def serialize_conflict(row) -> dict:
    return {
        'conflict_id': row.conflict_id,
        'conflict_type': row.conflict_type,
        'confidence': row.confidence,
        'verdict': row.verdict,
        'verdict_label': row.get_verdict_display(),
        'explanation': row.explanation,
        'authority_scores': row.authority_scores,
        'freshness_scores': row.freshness_scores,
        'claim_a': {
            'claim_id': row.claim_a.claim_id,
            'text': row.claim_a.normalized_text,
            'chunk_id': getattr(row.claim_a.source_chunk, 'chunk_id', ''),
            'authority_level': row.claim_a.authority_level,
        },
        'claim_b': {
            'claim_id': row.claim_b.claim_id,
            'text': row.claim_b.normalized_text,
            'chunk_id': getattr(row.claim_b.source_chunk, 'chunk_id', ''),
            'authority_level': row.claim_b.authority_level,
        },
    }
