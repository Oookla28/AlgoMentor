import pytest

from apps.knowledge.services.evidence_schema import evidence_from_chunk, evidence_from_media
from apps.knowledge.services.mime_router import detect_mime, route_for_path
from apps.knowledge.services.multimodal_loader import load_any
from core.exceptions import KnowledgeRetrievalError, ValidationError


def test_text_and_markdown_loading(tmp_path):
    text_file = tmp_path / 'notes.txt'
    text_file.write_text('循环队列判满条件是队尾加一等于队头。', encoding='utf-8')
    parsed = load_any(text_file)
    assert parsed.source_type == 'text'
    assert parsed.document.pages[0].text.startswith('循环队列')
    assert not parsed.warnings

    markdown = tmp_path / 'lecture.md'
    markdown.write_text('# 第三章 队列\n\n循环队列判满条件。', encoding='utf-8')
    parsed = load_any(markdown)
    assert parsed.source_type == 'markdown'
    assert parsed.parser_name == 'markdown'


def test_unsupported_mime_and_missing_file(tmp_path):
    unsupported = tmp_path / 'unknown.xyz'
    unsupported.write_bytes(b'data')
    with pytest.raises(ValidationError):
        load_any(unsupported)
    with pytest.raises(ValidationError):
        load_any(tmp_path / 'missing.txt')


def test_empty_text_file_is_rejected(tmp_path):
    empty = tmp_path / 'empty.txt'
    empty.write_text('   ', encoding='utf-8')
    with pytest.raises(KnowledgeRetrievalError):
        load_any(empty)


def test_image_metadata_annotation_and_optional_ocr(tmp_path, settings):
    settings.EVIDENCE_RAG_OCR_ENABLED = True
    image_path = tmp_path / 'queue.png'
    try:
        from PIL import Image
    except ImportError:
        pytest.skip('Pillow unavailable')
    Image.new('RGB', (12, 8), color=(20, 120, 100)).save(image_path)
    parsed = load_any(image_path, annotation='循环队列示意图，队头在左，队尾在右。')
    assert parsed.document.pages[0].text.startswith('循环队列示意图')
    assert parsed.media and parsed.media[0].modality == 'image'
    assert parsed.media[0].manual_annotation
    assert parsed.media[0].metadata.get('width') == 12
    assert any(warning in ('OCR_UNAVAILABLE', 'OCR_FAILED') for warning in parsed.warnings)


def test_video_annotation_without_ffmpeg_still_yields_evidence(tmp_path, settings):
    settings.EVIDENCE_RAG_ASR_ENABLED = True
    video = tmp_path / 'lecture.mp4'
    video.write_bytes(b'not a real video')
    parsed = load_any(video, annotation='视频 03:20 处演示循环队列判满。', caption='循环队列讲解')
    assert parsed.media and parsed.media[0].modality == 'video'
    assert parsed.document.pages[0].text.startswith('视频 03:20')
    assert any(warning in ('FFMPEG_UNAVAILABLE', 'FFPROBE_FAILED', 'ASR_UNAVAILABLE', 'ASR_FAILED') for warning in parsed.warnings)


def test_mime_routing():
    assert route_for_path(__import__('pathlib').Path('a.pdf')) == 'pdf'
    assert route_for_path(__import__('pathlib').Path('a.md')) == 'markdown'
    assert detect_mime(__import__('pathlib').Path('a.png')) == 'image/png'


def test_evidence_schema_from_media_and_chunk():
    from types import SimpleNamespace
    media = SimpleNamespace(
        asset_id='image-1', document_id=1, modality='image', caption='图', ocr_text='ocr', asr_text='',
        manual_annotation='人工标注', bbox=[0, 0, 1, 1], start_time=None, end_time=None,
        parser_confidence=0.8, sha256='a' * 64, version='1', metadata={'parser': 'manual'},
        created_at=None, page_number=1, document=SimpleNamespace(authority_level=1, source_type='image'),
    )
    unit = evidence_from_media(media)
    assert unit.evidence_id == 'media:image-1'
    assert unit.text == '人工标注'
    assert unit.bbox == [0, 0, 1, 1]
    chunk = SimpleNamespace(
        chunk_id='c1', parent_chunk=None, media_asset=media, content='文本', page_number=2,
        parser_confidence=0.9, content_hash='b' * 64, version='1', heading_path='第一章',
        char_start=1, char_end=3, source_type='original',
        document=SimpleNamespace(pk=1, parser_name='pypdf', created_at=None, authority_level=2),
    )
    unit = evidence_from_chunk(chunk)
    assert unit.evidence_id == 'chunk:c1'
    assert unit.chunk_id == 'c1'
    assert unit.modality == 'image'
