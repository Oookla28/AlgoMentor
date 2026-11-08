"""Capability health probes.

States are intentionally explicit:
available / fallback / disabled / environment-limited / unverified / not-configured.
No probe downloads a model, calls a paid API or queries Wikipedia.
"""

import importlib.util
import shutil
import socket

from django.conf import settings
from django.db import connection


def _entry(name, state, reason='', **details):
    return {'name': name, 'state': state, 'reason': reason, 'details': details}


def _database():
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
            cursor.fetchone()
        return _entry('database', 'available', provider='sqlite')
    except Exception as exc:
        return _entry('database', 'environment-limited', type(exc).__name__)


def _indexes():
    from apps.knowledge.models import KnowledgeDocument
    legacy = KnowledgeDocument.objects.exclude(index_version='').exclude(collection_name='')
    advanced = KnowledgeDocument.objects.exclude(latest_index_version='')
    legacy_count = legacy.count()
    advanced_count = advanced.count()
    advanced_detail = {}
    if advanced_count:
        document = advanced.order_by('-created_at').first()
        advanced_detail = {
            'index_version': document.latest_index_version,
            'embedding_identity': ((document.source_metadata or {}).get('advanced') or {}).get('embedding_identity', ''),
            'collection_name': ((document.source_metadata or {}).get('advanced') or {}).get('collection_name', ''),
            'dimension': ((document.source_metadata or {}).get('advanced') or {}).get('embedding_dimension', 0),
            'provider': getattr(settings, 'EMBEDDING_PROVIDER', ''),
            'model': 'char-1-3:2048' if getattr(settings, 'EMBEDDING_PROVIDER', '') == 'tfidf' else getattr(settings, 'EMBEDDING_MODEL', ''),
            'threshold': getattr(settings, 'EVIDENCE_RAG_MIN_RERANK_SCORE', 0.12),
        }
        try:
            import chromadb
            client = chromadb.PersistentClient(path=str(settings.CHROMA_PATH))
            collection = client.get_collection(name=advanced_detail['collection_name'])
            advanced_detail['vector_count'] = collection.count()
            state, reason = 'available', ''
        except Exception as exc:
            state, reason = 'fallback', f'chroma_collection_unavailable:{type(exc).__name__}'
    else:
        state, reason = 'disabled', 'no_advanced_index'
    return [
        _entry('legacy_index', 'available' if legacy_count else 'disabled', '' if legacy_count else 'no_legacy_index', documents=legacy_count),
        _entry('advanced_index', state, reason, documents=advanced_count, **advanced_detail),
    ]


def _embedding():
    provider = getattr(settings, 'EMBEDDING_PROVIDER', 'bge')
    if provider == 'tfidf':
        return _entry('embedding', 'fallback', 'tfidf_lexical_baseline_not_bge', provider='tfidf', model='char-1-3:2048', dimension=2048)
    if provider != 'bge':
        return _entry('embedding', 'disabled', 'unsupported_provider', provider=provider)
    if importlib.util.find_spec('sentence_transformers') is None:
        return _entry('embedding', 'environment-limited', 'sentence_transformers_missing', provider='bge', model=settings.EMBEDDING_MODEL)
    from pathlib import Path
    cache = Path.home() / '.cache/huggingface/hub' / ('models--' + settings.EMBEDDING_MODEL.replace('/', '--'))
    if cache.is_dir():
        return _entry('embedding', 'unverified', 'weights_present_but_model_not_loaded', provider='bge', model=settings.EMBEDDING_MODEL, revision=settings.EMBEDDING_REVISION, dimension=512)
    return _entry('embedding', 'unverified', 'local_weights_not_found', provider='bge', model=settings.EMBEDDING_MODEL, revision=settings.EMBEDDING_REVISION, dimension=512)


def _reranker():
    backend = getattr(settings, 'EVIDENCE_RAG_RERANK_BACKEND', 'deterministic')
    if backend == 'deterministic':
        return _entry('reranker', 'available', 'deterministic_backend', backend='deterministic')
    if importlib.util.find_spec('sentence_transformers') is None:
        return _entry('reranker', 'fallback', 'cross_encoder_dependency_missing', backend='deterministic')
    return _entry('reranker', 'unverified', 'cross_encoder_model_not_probed', backend='cross_encoder', model=settings.EVIDENCE_RAG_CROSS_ENCODER_MODEL)


def _llm():
    return _entry('llm', 'not-configured', 'per_user_byok', provider='DeepSeek', model='user-selected', network_probe=False)


def _piston():
    try:
        with socket.create_connection(('127.0.0.1', 2000), timeout=0.3):
            return _entry('piston', 'available', 'localhost_2000_open', endpoint='127.0.0.1:2000')
    except OSError:
        return _entry('piston', 'environment-limited', 'localhost_2000_not_open', endpoint='127.0.0.1:2000')


def _optional_binary(package, binary, name):
    has_package = importlib.util.find_spec(package) is not None
    has_binary = shutil.which(binary) is not None
    if has_package and has_binary:
        return _entry(name, 'available', '', package=package, binary=binary)
    if has_package or has_binary:
        missing = 'binary' if has_package else 'package'
        return _entry(name, 'environment-limited', f'{missing}_missing', package=has_package, binary=has_binary)
    return _entry(name, 'disabled', 'optional_dependency_missing', package=False, binary=False)


def _wikipedia():
    if not getattr(settings, 'WIKIPEDIA_ENABLED', True):
        return _entry('wikipedia', 'disabled', 'disabled_by_setting')
    return _entry('wikipedia', 'unverified', 'network_not_probed', provider='Wikipedia Action API')


def probe_capabilities():
    entries = [_entry('django', 'available', '', version=__import__('django').get_version()), _database()]
    entries.extend(_indexes())
    entries.append(_embedding())
    entries.append(_reranker())
    entries.append(_llm())
    entries.append(_piston())
    entries.append(_optional_binary('pytesseract', 'tesseract', 'ocr'))
    entries.append(_optional_binary('faster_whisper', 'ffmpeg', 'asr'))
    entries.append(_optional_binary('cv2', 'ffmpeg', 'keyframes'))
    entries.append(_wikipedia())
    return entries


def capability_map():
    return {entry['name']: entry for entry in probe_capabilities()}
