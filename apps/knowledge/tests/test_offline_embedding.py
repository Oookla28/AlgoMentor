"""Runtime must use installed local weights, preserving the existing index identity."""
from types import SimpleNamespace
from unittest.mock import Mock
import sys

import pytest
from core.exceptions import KnowledgeRetrievalError
from apps.knowledge.services.embedding_service import BGEEmbeddings, embedding_identity


def test_bge_queries_use_pinned_local_weights_without_remote_download(settings, monkeypatch):
    factory = Mock()
    monkeypatch.setitem(sys.modules, 'sentence_transformers', SimpleNamespace(SentenceTransformer=factory))
    settings.LOCAL_EMBEDDING_OFFLINE_MODE = True
    BGEEmbeddings()
    assert factory.call_args.kwargs['local_files_only'] is True
    assert factory.call_args.kwargs['revision'] == settings.EMBEDDING_REVISION
    assert embedding_identity() == f'bge:{settings.EMBEDDING_MODEL}:{settings.EMBEDDING_REVISION}'


def test_missing_local_weights_fail_clearly_without_changing_model(settings, monkeypatch):
    factory = Mock(side_effect=OSError('No cached weights'))
    monkeypatch.setitem(sys.modules, 'sentence_transformers', SimpleNamespace(SentenceTransformer=factory))
    settings.LOCAL_EMBEDDING_OFFLINE_MODE = True
    with pytest.raises(KnowledgeRetrievalError) as error:
        BGEEmbeddings()
    assert error.value.code == 'EMBEDDING_UNAVAILABLE'
    assert 'prepare_embedding_model' in error.value.message
    assert factory.call_count == 1
