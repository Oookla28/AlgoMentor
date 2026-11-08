import shutil
from pathlib import Path

import pytest
from django.core.management import call_command

from apps.knowledge.models import KnowledgeChunk, KnowledgeDocument


@pytest.mark.django_db
def test_advanced_command_builds_both_indexes_and_legacy_rebuild_keeps_advanced_chunks(settings, tmp_path):
    settings.EMBEDDING_PROVIDER = 'tfidf'
    settings.EMBEDDING_MODEL = 'tfidf'
    settings.EMBEDDING_REVISION = 'v1'
    settings.CHROMA_PATH = tmp_path / 'chroma'
    settings.BASE_DIR = tmp_path
    source = tmp_path / 'knowledge/original/数据结构与算法知识库文档.pdf'
    source.parent.mkdir(parents=True)
    shutil.copy2(Path(__file__).resolve().parents[3] / 'knowledge/original/数据结构与算法知识库文档.pdf', source)

    call_command('ingest_knowledge', path=str(source), advanced=True, verbosity=0)
    document = KnowledgeDocument.objects.get()
    assert document.index_version
    assert document.latest_index_version.startswith('adv-')
    assert document.ingestion_status == 'ready'
    assert document.chunks.filter(chunk_type='legacy').exists()
    assert document.chunks.filter(chunk_type='parent').exists()
    assert document.chunks.filter(chunk_type='child').exists()
    parent_pks = set(document.chunks.filter(chunk_type='parent').values_list('pk', flat=True))
    assert set(document.chunks.filter(chunk_type='child').values_list('parent_chunk_id', flat=True)) <= parent_pks
    assert all(child.parent_chunk and child.parent_chunk.chunk_type == 'parent' for child in document.chunks.filter(chunk_type='child')[:10])

    advanced_count = document.chunks.filter(chunk_type__in=['parent', 'child']).count()
    call_command('ingest_knowledge', path=str(source), rebuild=True, verbosity=0)
    document.refresh_from_db()
    assert document.chunks.filter(chunk_type__in=['parent', 'child']).count() == advanced_count
    assert document.latest_index_version.startswith('adv-')


@pytest.mark.django_db
def test_advanced_only_command_accepts_markdown(settings, tmp_path):
    settings.EMBEDDING_PROVIDER = 'tfidf'
    settings.EMBEDDING_MODEL = 'tfidf'
    settings.EMBEDDING_REVISION = 'v1'
    settings.CHROMA_PATH = tmp_path / 'chroma'
    settings.BASE_DIR = tmp_path
    source = tmp_path / 'lecture.md'
    source.write_text('# 第三章 队列\n\n循环队列判满条件是队尾加一等于队头。\n\n' + ('队列操作的时间复杂度为 O(1)。\n\n' * 30), encoding='utf-8')
    call_command('ingest_knowledge', path=str(source), advanced_only=True, verbosity=0)
    document = KnowledgeDocument.objects.get()
    assert document.source_type == 'markdown'
    assert document.latest_index_version.startswith('adv-')
    assert document.chunks.filter(chunk_type='child').exists()
    assert not document.chunks.filter(chunk_type='legacy').exists()
