"""Persist evidence, claims and conflict sets without storing chain-of-thought."""

import re

from django.utils.dateparse import parse_datetime

from apps.platform.contracts import ClaimUnit, EvidenceUnit

_NEGATION_RE = re.compile(r'(不|非|无|未|不能|不会|禁止|没有|并非|不是)')
_NUMBER_RE = re.compile(r'-?\d+(?:\.\d+)?')
_UNIT_RE = re.compile(r'\d+\s*(个|次|层|位|种|字节|比特)')
_VERSION_RE = re.compile(r'v?\d+\.\d+(?:\.\d+)?', re.I)
_YEAR_RE = re.compile(r'\d{4}\s*年')


def _authority(level: int) -> float:
    return max(0.0, min(1.0, 1 - (int(level or 3) - 1) / 4))


def evidence_from_item(item: dict, provider: str = '', index_version: str = '') -> EvidenceUnit:
    return EvidenceUnit(
        evidence_id=f"chunk:{item.get('chunk_id', '')}",
        parent_id=item.get('parent_chunk_id', ''),
        document_id=item.get('document_id'),
        chunk_id=item.get('chunk_id', ''),
        source_uri=f"/knowledge/source/{item.get('chunk_id', '')}/",
        modality=item.get('modality', 'text'),
        page=item.get('page'),
        char_start=item.get('char_start'),
        char_end=item.get('char_end'),
        content_hash=item.get('content_hash', ''),
        source_version=str(item.get('source_version', '1')),
        authority_score=_authority(item.get('authority_level', 3)),
        retrieval_score=float(item.get('retrieval_score', 0.0) or 0.0),
        content=item.get('content', ''),
        heading_path=item.get('heading_path', ''),
        provider=provider,
        index_version=index_version,
    )


def persist_evidence(run, items, provider='', index_version=''):
    from apps.platform.models import Evidence
    saved = {}
    for item in items:
        unit = evidence_from_item(item, provider, index_version)
        if not unit.chunk_id:
            continue
        row, _created = Evidence.objects.update_or_create(
            run=run, evidence_id=unit.evidence_id,
            defaults={
                'parent_id': unit.parent_id, 'document_id': unit.document_id, 'chunk_id': unit.chunk_id,
                'source_uri': unit.source_uri, 'modality': unit.modality, 'page': unit.page,
                'char_start': unit.char_start, 'char_end': unit.char_end, 'content_hash': unit.content_hash,
                'source_version': unit.source_version, 'authority_score': unit.authority_score,
                'retrieval_score': unit.retrieval_score, 'verifier_score': unit.verifier_score,
                'content': unit.content, 'heading_path': unit.heading_path,
                'provider': unit.provider, 'index_version': unit.index_version,
            },
        )
        saved[unit.evidence_id] = row
    return saved


def _claim_unit(text: str, evidence_ids):
    numbers = tuple(dict.fromkeys(_NUMBER_RE.findall(text)))[:8]
    units = tuple(dict.fromkeys(' '.join(value) for value in _UNIT_RE.findall(text)))[:8]
    versions = tuple(dict.fromkeys(_VERSION_RE.findall(text)))[:8]
    years = tuple(dict.fromkeys(_YEAR_RE.findall(text)))[:8]
    return ClaimUnit(
        claim_id='',
        text=text,
        polarity='negative' if _NEGATION_RE.search(text) else 'positive',
        numbers=numbers,
        units=units,
        versions=versions,
        years=years,
        evidence_ids=tuple(evidence_ids),
        status='supported' if evidence_ids else 'unsupported',
    )


def persist_claims(run, evidence_rows):
    from apps.knowledge.services.claim_service import extract_claims
    from apps.platform.models import Claim
    saved = []
    for evidence in evidence_rows:
        for extracted in extract_claims(evidence.content, evidence.chunk_id):
            unit = _claim_unit(extracted.normalized_text, [evidence.evidence_id])
            row, _created = Claim.objects.update_or_create(
                run=run, claim_id=extracted.claim_id,
                defaults={
                    'text': unit.text, 'polarity': unit.polarity, 'numbers': list(unit.numbers),
                    'units': list(unit.units), 'versions': list(unit.versions), 'years': list(unit.years),
                    'evidence_ids': list(unit.evidence_ids), 'status': unit.status,
                },
            )
            saved.append(row)
    return saved


def persist_conflicts(run, conflicts):
    from apps.platform.models import ConflictSet
    saved = []
    for conflict in conflicts:
        row, _created = ConflictSet.objects.update_or_create(
            run=run, conflict_id=conflict.conflict_id,
            defaults={
                'conflict_type': conflict.conflict_type,
                'confidence': conflict.confidence,
                'verdict': conflict.verdict,
                'claims': [
                    {'claim_id': conflict.claim_a_id},
                    {'claim_id': conflict.claim_b_id},
                ],
                'explanation': conflict.explanation,
            },
        )
        saved.append(row)
    return saved
