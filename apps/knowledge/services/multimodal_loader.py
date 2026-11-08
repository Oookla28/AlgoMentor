"""Adapter-based multimodal document loader.

Every optional dependency (python-docx, Pillow, pytesseract, faster-whisper,
ffmpeg) is imported lazily. Missing tools produce actionable warnings and an
honest low-confidence text fallback; Django startup and PDF RAG never depend
on them.
"""

from dataclasses import dataclass, field
import hashlib
from pathlib import Path
import shutil
import subprocess

from django.conf import settings

from core.exceptions import KnowledgeRetrievalError, ValidationError

from .document_loader import LoadedDocument, SourcePage, load_document
from .mime_router import detect_mime, is_media_route, route_for_path, source_type_for_route


@dataclass(frozen=True)
class MediaProbe:
    asset_id: str
    modality: str
    file_path: str
    mime_type: str
    sha256: str
    ocr_text: str = ''
    asr_text: str = ''
    caption: str = ''
    manual_annotation: str = ''
    parser_confidence: float = 0.0
    metadata: dict = field(default_factory=dict)


@dataclass(frozen=True)
class ParsedDocument:
    document: LoadedDocument
    source_type: str
    parser_name: str
    parser_version: str = ''
    media: tuple[MediaProbe, ...] = ()
    warnings: tuple[str, ...] = ()
    metadata: dict = field(default_factory=dict)


def _read_text(path: Path) -> str:
    for encoding in ('utf-8-sig', 'utf-8', 'gb18030'):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    raise KnowledgeRetrievalError('文本文件编码无法识别，请另存为 UTF-8。', code='TEXT_ENCODING_UNSUPPORTED')


def _asset_id(sha256: str, modality: str) -> str:
    return f'{modality}-{sha256[:16]}'


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def _image_metadata(path: Path):
    try:
        from PIL import Image
        with Image.open(path) as image:
            return {'width': image.width, 'height': image.height, 'format': image.format or ''}, ''
    except ImportError:
        return {}, 'PIL_UNAVAILABLE'
    except Exception:
        return {}, 'IMAGE_METADATA_UNREADABLE'


def _ocr_text(path: Path):
    try:
        import pytesseract
        from PIL import Image
        with Image.open(path) as image:
            return pytesseract.image_to_string(image, lang=getattr(settings, 'EVIDENCE_RAG_OCR_LANG', 'chi_sim+eng')).strip(), ''
    except ImportError:
        return '', 'OCR_UNAVAILABLE'
    except Exception:
        return '', 'OCR_FAILED'


def _video_metadata(path: Path):
    ffprobe = shutil.which('ffprobe')
    if not ffprobe:
        return {}, 'FFMPEG_UNAVAILABLE'
    try:
        process = subprocess.run(
            [ffprobe, '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', str(path)],
            capture_output=True, text=True, timeout=15, check=False,
        )
        duration = float(process.stdout.strip()) if process.stdout.strip() else None
        return {'duration': duration}, ''
    except Exception:
        return {}, 'FFPROBE_FAILED'


def _asr_text(path: Path):
    try:
        from faster_whisper import WhisperModel
        model = WhisperModel('small', device='cpu', compute_type='int8', download_root=str(Path(settings.BASE_DIR) / 'data/models'))
        segments, _info = model.transcribe(str(path), vad_filter=True)
        return '\n'.join(segment.text.strip() for segment in segments if segment.text.strip()), ''
    except ImportError:
        return '', 'ASR_UNAVAILABLE'
    except Exception:
        return '', 'ASR_FAILED'


def extract_keyframes(path: Path, output_dir: Path, count: int = 3):
    """Optional ffmpeg keyframe extraction. Returns (paths, warning)."""
    ffmpeg = shutil.which('ffmpeg')
    if not ffmpeg:
        return [], 'FFMPEG_UNAVAILABLE'
    output_dir.mkdir(parents=True, exist_ok=True)
    produced = []
    try:
        for index in range(1, max(1, count) + 1):
            target = output_dir / f'{path.stem}-frame-{index}.jpg'
            process = subprocess.run(
                [ffmpeg, '-y', '-ss', str(index * 3), '-i', str(path), '-frames:v', '1', str(target)],
                capture_output=True, text=True, timeout=30, check=False,
            )
            if process.returncode == 0 and target.is_file():
                produced.append(str(target))
        return produced, '' if produced else 'KEYFRAME_EXTRACTION_FAILED'
    except Exception:
        return produced, 'KEYFRAME_EXTRACTION_FAILED'


def _load_pdf(path: Path) -> ParsedDocument:
    loaded = load_document(path)
    return ParsedDocument(loaded, 'pdf', 'pypdf', getattr(__import__('pypdf'), '__version__', ''), metadata={'ocr_required': False})


def _load_docx(path: Path) -> ParsedDocument:
    try:
        import docx
    except ImportError:
        raise KnowledgeRetrievalError(
            '未安装可选依赖 python-docx，无法解析 DOCX。请安装 requirements-rag-multimodal.in 后重试；PDF/TXT/Markdown 不受影响。',
            code='OPTIONAL_DEPENDENCY_MISSING',
        ) from None
    try:
        document = docx.Document(str(path))
        paragraphs = [paragraph.text for paragraph in document.paragraphs if paragraph.text.strip()]
        for table in document.tables:
            rows = []
            for row in table.rows:
                rows.append(' | '.join(cell.text.strip() for cell in row.cells))
            if rows:
                paragraphs.append('\n'.join(rows))
    except Exception:
        raise KnowledgeRetrievalError('DOCX 文件损坏或无法解析。', code='DOCX_PARSE_FAILED') from None
    text = '\n\n'.join(paragraphs)
    if not text.strip():
        raise KnowledgeRetrievalError('DOCX 无可提取文本。', code='EMPTY_DOCUMENT')
    digest = _file_sha256(path)
    loaded = LoadedDocument(path, path.name, digest, (SourcePage(1, text),))
    return ParsedDocument(loaded, 'docx', 'python-docx', getattr(docx, '__version__', ''), metadata={'paragraphs': len(document.paragraphs), 'tables': len(document.tables)})


def _load_plain(path: Path, source_type: str) -> ParsedDocument:
    text = _read_text(path)
    if not text.strip():
        raise KnowledgeRetrievalError('文本文件为空。', code='EMPTY_DOCUMENT')
    digest = _file_sha256(path)
    loaded = LoadedDocument(path, path.name, digest, (SourcePage(1, text),))
    parser = 'markdown' if source_type == 'markdown' else 'plain-text'
    return ParsedDocument(loaded, source_type, parser, '')


def _load_media(path: Path, route: str, annotation: str = '', caption: str = '', enable_ocr=None, enable_asr=None) -> ParsedDocument:
    digest = _file_sha256(path)
    mime = detect_mime(path)
    warnings = []
    metadata = {}
    ocr_text = ''
    asr_text = ''
    confidence = 0.4
    if route == 'image':
        metadata, warning = _image_metadata(path)
        if warning:
            warnings.append(warning)
        enable_ocr = getattr(settings, 'EVIDENCE_RAG_OCR_ENABLED', False) if enable_ocr is None else enable_ocr
        if enable_ocr:
            ocr_text, warning = _ocr_text(path)
            if warning:
                warnings.append(warning)
            elif ocr_text:
                confidence = 0.7
    elif route in ('video', 'audio'):
        metadata, warning = _video_metadata(path)
        if warning:
            warnings.append(warning)
        enable_asr = getattr(settings, 'EVIDENCE_RAG_ASR_ENABLED', False) if enable_asr is None else enable_asr
        if enable_asr:
            asr_text, warning = _asr_text(path)
            if warning:
                warnings.append(warning)
            elif asr_text:
                confidence = 0.65
    text = annotation or caption or ocr_text or asr_text
    if not text:
        text = f'{route} 证据：{path.name}。当前未提供人工标注、OCR 或 ASR 文本，检索只能依据文件名与元数据。'
        warnings.append('NO_TEXT_EVIDENCE')
    probe = MediaProbe(
        asset_id=_asset_id(digest, route),
        modality=route,
        file_path=str(path),
        mime_type=mime,
        sha256=digest,
        ocr_text=ocr_text,
        asr_text=asr_text,
        caption=caption,
        manual_annotation=annotation,
        parser_confidence=confidence,
        metadata=metadata,
    )
    loaded = LoadedDocument(path, path.name, digest, (SourcePage(1, text),))
    return ParsedDocument(loaded, route, f'{route}-metadata', '', (probe,), tuple(warnings), metadata)


def load_any(path, annotation: str = '', caption: str = '', enable_ocr=None, enable_asr=None) -> ParsedDocument:
    path = Path(path)
    if not path.is_file():
        raise ValidationError('上传文件不存在。', code='FILE_NOT_FOUND')
    route = route_for_path(path)
    if is_media_route(route):
        return _load_media(path, route, annotation, caption, enable_ocr, enable_asr)
    if route == 'pdf':
        return _load_pdf(path)
    if route == 'docx':
        return _load_docx(path)
    return _load_plain(path, source_type_for_route(route))
