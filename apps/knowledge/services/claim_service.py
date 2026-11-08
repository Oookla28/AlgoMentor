"""Rule-based claim extraction. NLI/LLM detectors can be added as optional backends later."""

from dataclasses import dataclass
import hashlib
import re
import unicodedata

from django.conf import settings


@dataclass(frozen=True)
class ExtractedClaim:
    claim_id: str
    subject: str
    predicate: str
    object: str
    normalized_text: str
    contradiction_group: str
    detector_score: float


_SENTENCE_SPLIT_RE = re.compile(r'(?<=[。！？；!?;])\s*|\n+')
_CLAIM_PATTERN = re.compile(r'(.{1,40}?)(是|为|表示|指的是|定义为|包括|包含|由|有|等于)(.{1,120})')
_CODE_HINT_RE = re.compile(r'(\{|\}|```|def\s|class\s|printf|return\s|；\s*\n)')
_NORMALIZE_RE = re.compile(r'[\s，。！？；：、,.!?;:\-—_()（）\[\]【】"\']+')


def _normalize(text: str) -> str:
    return _NORMALIZE_RE.sub('', unicodedata.normalize('NFKC', text)).lower()


def extract_claims(text: str, chunk_id: str = '', max_claims: int | None = None) -> list[ExtractedClaim]:
    max_claims = max_claims or getattr(settings, 'EVIDENCE_RAG_MAX_CLAIMS_PER_CHUNK', 6)
    claims = []
    seen = set()
    for sentence in _SENTENCE_SPLIT_RE.split(text or ''):
        sentence = sentence.strip()
        if len(sentence) < 8 or len(sentence) > 300:
            continue
        if _CODE_HINT_RE.search(sentence):
            continue
        normalized = _normalize(sentence)
        if len(normalized) < 6 or normalized in seen:
            continue
        seen.add(normalized)
        match = _CLAIM_PATTERN.search(sentence)
        if match:
            subject, predicate, object_ = match.group(1).strip(), match.group(2), match.group(3).strip()
        else:
            subject, predicate, object_ = sentence[:40], '陈述', sentence
        identity = hashlib.sha256(f'{chunk_id}|{normalized}'.encode('utf-8')).hexdigest()[:32]
        group = hashlib.sha256(_normalize(subject).encode('utf-8')).hexdigest()[:16] if len(_normalize(subject)) >= 2 else ''
        claims.append(ExtractedClaim(
            claim_id=identity,
            subject=subject[:500],
            predicate=predicate,
            object=object_[:1000],
            normalized_text=sentence,
            contradiction_group=group,
            detector_score=0.6 if match else 0.4,
        ))
        if len(claims) >= max_claims:
            break
    return claims


def extract_and_store_claims(chunks):
    """Upsert claims for selected chunks; stale claims of the same chunks are removed."""
    from apps.knowledge.models import EvidenceClaim
    stored = []
    for chunk in chunks:
        extracted = extract_claims(chunk.content, chunk.chunk_id)
        ids = [claim.claim_id for claim in extracted]
        chunk.claims.exclude(claim_id__in=ids).delete()
        for claim in extracted:
            row, _created = EvidenceClaim.objects.update_or_create(
                claim_id=claim.claim_id,
                defaults={
                    'source_chunk': chunk,
                    'subject': claim.subject,
                    'predicate': claim.predicate,
                    'object': claim.object,
                    'normalized_text': claim.normalized_text,
                    'valid_from': chunk.document.valid_from,
                    'valid_to': chunk.document.valid_to,
                    'authority_level': chunk.document.authority_level,
                    'contradiction_group': claim.contradiction_group,
                    'detector_score': claim.detector_score,
                },
            )
            stored.append(row)
    return stored
