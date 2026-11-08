"""MIME detection and loader routing.

Only the standard library is required. Every optional parser is imported
lazily by :mod:`multimodal_loader`, so a missing dependency can never stop
Django from starting.
"""

from pathlib import Path
from core.exceptions import ValidationError

TEXT_SUFFIXES = {'.txt', '.text', '.log', '.csv', '.tsv', '.json', '.yaml', '.yml', '.py', '.java', '.c', '.cpp', '.md', '.markdown'}
DOCX_SUFFIXES = {'.docx'}
PDF_SUFFIXES = {'.pdf'}
IMAGE_SUFFIXES = {'.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp', '.tif', '.tiff'}
VIDEO_SUFFIXES = {'.mp4', '.mov', '.mkv', '.webm', '.avi', '.m4v'}
AUDIO_SUFFIXES = {'.mp3', '.wav', '.m4a', '.aac', '.flac', '.ogg'}

MIME_BY_SUFFIX = {
    '.pdf': 'application/pdf',
    '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    '.md': 'text/markdown',
    '.markdown': 'text/markdown',
    '.txt': 'text/plain',
    '.text': 'text/plain',
    '.png': 'image/png',
    '.jpg': 'image/jpeg',
    '.jpeg': 'image/jpeg',
    '.gif': 'image/gif',
    '.webp': 'image/webp',
    '.bmp': 'image/bmp',
    '.tif': 'image/tiff',
    '.tiff': 'image/tiff',
    '.mp4': 'video/mp4',
    '.mov': 'video/quicktime',
    '.mkv': 'video/x-matroska',
    '.webm': 'video/webm',
    '.avi': 'video/x-msvideo',
    '.mp3': 'audio/mpeg',
    '.wav': 'audio/wav',
    '.m4a': 'audio/mp4',
    '.flac': 'audio/flac',
}

SUPPORTED_LABELS = {
    'pdf': 'PDF',
    'docx': 'DOCX',
    'markdown': 'Markdown',
    'text': '纯文本',
    'image': '图片',
    'video': '视频',
    'audio': '音频',
}


def detect_mime(path: Path, declared: str = '') -> str:
    if declared:
        declared = declared.split(';', 1)[0].strip().lower()
        if '/' in declared:
            return declared
    return MIME_BY_SUFFIX.get(Path(path).suffix.lower(), 'application/octet-stream')


def route_for_path(path: Path) -> str:
    suffix = Path(path).suffix.lower()
    if suffix in PDF_SUFFIXES:
        return 'pdf'
    if suffix in DOCX_SUFFIXES:
        return 'docx'
    if suffix in {'.md', '.markdown'}:
        return 'markdown'
    if suffix in TEXT_SUFFIXES:
        return 'text'
    if suffix in IMAGE_SUFFIXES:
        return 'image'
    if suffix in VIDEO_SUFFIXES:
        return 'video'
    if suffix in AUDIO_SUFFIXES:
        return 'audio'
    raise ValidationError(f'不支持的文件类型：{suffix or "无扩展名"}。支持 PDF、DOCX、Markdown、纯文本、常见图片与音视频。', code='UNSUPPORTED_MIME')


def route_for_mime(mime: str) -> str:
    mime = (mime or '').split(';', 1)[0].strip().lower()
    if mime == 'application/pdf':
        return 'pdf'
    if mime == 'application/vnd.openxmlformats-officedocument.wordprocessingml.document':
        return 'docx'
    if mime == 'text/markdown':
        return 'markdown'
    if mime.startswith('text/'):
        return 'text'
    if mime.startswith('image/'):
        return 'image'
    if mime.startswith('video/'):
        return 'video'
    if mime.startswith('audio/'):
        return 'audio'
    raise ValidationError(f'不支持的文件类型：{mime or "未知"}。', code='UNSUPPORTED_MIME')


def source_type_for_route(route: str) -> str:
    return route


def is_media_route(route: str) -> bool:
    return route in ('image', 'video', 'audio')
