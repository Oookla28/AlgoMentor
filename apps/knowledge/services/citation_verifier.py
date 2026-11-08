"""Claim-level citation verification on top of the legacy [来源N] contract."""

import re

from .sparse_retrieval import tokenize

_CITATION_RE = re.compile(r'\[来源(\d+)\]')
# Keep a trailing [来源N] attached to the sentence it supports.
_SENTENCE_SPLIT_RE = re.compile(r'(?<=[。！？；!?;])(?!\s*\[来源\d+\])\s*|\n+')
_FACT_CUE_RE = re.compile(r'(是|为|表示|指的是|包括|包含|等于|复杂度|时间复杂度|空间复杂度|O\(|定义|性质|结论)', re.I)
_NEGATION_RE = re.compile(r'(不|非|无|未|不能|不会|禁止|没有|并非|不是)')


def split_claims(answer: str):
    return [sentence.strip() for sentence in _SENTENCE_SPLIT_RE.split(answer or '') if sentence.strip()]


def verify_answer(answer: str, citations) -> dict:
    citations = list(citations or [])
    cited_ids = sorted({int(value) for value in _CITATION_RE.findall(answer or '')})
    out_of_range = [value for value in cited_ids if value < 1 or value > len(citations)]
    missing = []
    unsupported = []
    contradictions = []
    factual_claims = 0
    cited_factual_claims = 0
    for sentence in split_claims(answer):
        refs = [int(value) for value in _CITATION_RE.findall(sentence)]
        body = _CITATION_RE.sub('', sentence).strip()
        if len(body) < 8 or body.endswith(('？', '?')):
            continue
        is_factual = bool(refs) or bool(_FACT_CUE_RE.search(body))
        if not is_factual:
            continue
        factual_claims += 1
        if not refs:
            missing.append(body[:200])
            continue
        cited_factual_claims += 1
        valid_refs = [value for value in refs if 1 <= value <= len(citations)]
        if not valid_refs:
            continue
        claim_tokens = set(tokenize(body))
        if not claim_tokens:
            continue
        best_overlap = 0.0
        best_content = ''
        for value in valid_refs:
            content = citations[value - 1].content
            content_tokens = set(tokenize(content))
            overlap = len(claim_tokens & content_tokens) / len(claim_tokens) if claim_tokens else 0.0
            if overlap > best_overlap:
                best_overlap, best_content = overlap, content
        if best_overlap < 0.12:
            unsupported.append({'claim': body[:200], 'citations': valid_refs, 'overlap': round(best_overlap, 4)})
        elif _NEGATION_RE.search(body) != _NEGATION_RE.search(best_content) and best_overlap >= 0.3:
            contradictions.append({'claim': body[:200], 'citations': valid_refs, 'overlap': round(best_overlap, 4)})
    coverage = round(cited_factual_claims / factual_claims, 4) if factual_claims else 1.0
    return {
        'valid': not out_of_range,
        'cited_ids': cited_ids,
        'out_of_range': out_of_range,
        'missing_citations': missing[:20],
        'unsupported_claims': unsupported[:20],
        'contradictions': contradictions[:20],
        'factual_claims': factual_claims,
        'cited_factual_claims': cited_factual_claims,
        'claim_coverage': coverage,
        'passed': not out_of_range and not unsupported and not contradictions,
    }
