"""Unified evidence shape shared by text, image and video retrieval.

The schema is deliberately plain: it is serialisable to JSON, can be built
from an ORM row without importing Django models at module import time, and
never carries credentials or private filesystem details into prompts.
"""

from dataclasses import asdict, dataclass, field


@dataclass(frozen=True)
class EvidenceUnit:
    evidence_id: str
    document_id: int | None = None
    chunk_id: str = ''
    parent_chunk_id: str = ''
    modality: str = 'text'
    text: str = ''
    caption: str = ''
    ocr_text: str = ''
    asr_text: str = ''
    source_uri: str = ''
    page_number: int | None = None
    bbox: list = field(default_factory=list)
    start_time: float | None = None
    end_time: float | None = None
    confidence: float = 0.0
    sha256: str = ''
    version: str = '1'
    parser: str = ''
    created_at: str = ''
    heading_path: str = ''
    char_start: int | None = None
    char_end: int | None = None
    authority_level: int = 3
    source_type: str = 'original'

    def to_dict(self) -> dict:
        return asdict(self)


def evidence_from_chunk(chunk) -> EvidenceUnit:
    document = getattr(chunk, 'document', None)
    parent = getattr(chunk, 'parent_chunk', None)
    media = getattr(chunk, 'media_asset', None)
    modality = 'text'
    if media is not None:
        modality = media.modality
    return EvidenceUnit(
        evidence_id=f'chunk:{chunk.chunk_id}',
        document_id=getattr(document, 'pk', None),
        chunk_id=chunk.chunk_id,
        parent_chunk_id=getattr(parent, 'chunk_id', '') if parent else '',
        modality=modality,
        text=chunk.content,
        caption=getattr(media, 'caption', '') if media else '',
        ocr_text=getattr(media, 'ocr_text', '') if media else '',
        asr_text=getattr(media, 'asr_text', '') if media else '',
        source_uri=f'/knowledge/source/{chunk.chunk_id}/',
        page_number=chunk.page_number,
        bbox=list(getattr(media, 'bbox', []) or []) if media else [],
        start_time=getattr(media, 'start_time', None) if media else None,
        end_time=getattr(media, 'end_time', None) if media else None,
        confidence=chunk.parser_confidence,
        sha256=chunk.content_hash,
        version=chunk.version,
        parser=getattr(document, 'parser_name', '') if document else '',
        created_at=document.created_at.isoformat() if document and document.created_at else '',
        heading_path=chunk.heading_path,
        char_start=chunk.char_start,
        char_end=chunk.char_end,
        authority_level=getattr(document, 'authority_level', 3) if document else 3,
        source_type=chunk.source_type,
    )


def evidence_from_media(asset) -> EvidenceUnit:
    text = asset.manual_annotation or asset.caption or asset.ocr_text or asset.asr_text or asset.asset_id
    return EvidenceUnit(
        evidence_id=f'media:{asset.asset_id}',
        document_id=asset.document_id,
        chunk_id='',
        modality=asset.modality,
        text=text,
        caption=asset.caption,
        ocr_text=asset.ocr_text,
        asr_text=asset.asr_text,
        source_uri=f'/api/v1/knowledge/media/{asset.asset_id}/file/',
        page_number=asset.page_number,
        bbox=list(asset.bbox or []),
        start_time=asset.start_time,
        end_time=asset.end_time,
        confidence=asset.parser_confidence,
        sha256=asset.sha256,
        version=asset.version,
        parser=str((asset.metadata or {}).get('parser', 'manual')),
        created_at=asset.created_at.isoformat() if asset.created_at else '',
        authority_level=getattr(asset.document, 'authority_level', 3) if asset.document_id else 3,
        source_type=getattr(asset.document, 'source_type', 'image') if asset.document_id else 'image',
    )
