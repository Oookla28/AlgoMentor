"""Platform evidence and claim contracts shared by the agent and evaluation layers."""

from dataclasses import asdict, dataclass, field


@dataclass(frozen=True)
class EvidenceUnit:
    evidence_id: str
    parent_id: str = ''
    document_id: int | None = None
    chunk_id: str = ''
    source_uri: str = ''
    modality: str = 'text'
    page: int | None = None
    char_start: int | None = None
    char_end: int | None = None
    content_hash: str = ''
    source_version: str = '1'
    valid_from: str = ''
    valid_to: str = ''
    authority_score: float = 0.0
    retrieval_score: float = 0.0
    verifier_score: float = 0.0
    content: str = ''
    heading_path: str = ''
    provider: str = ''
    index_version: str = ''

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ClaimUnit:
    claim_id: str
    text: str
    polarity: str = 'positive'
    numbers: tuple[str, ...] = ()
    units: tuple[str, ...] = ()
    versions: tuple[str, ...] = ()
    years: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()
    status: str = 'supported'

    def to_dict(self) -> dict:
        payload = asdict(self)
        for key in ('numbers', 'units', 'versions', 'years', 'evidence_ids'):
            payload[key] = list(payload[key])
        return payload
