import hashlib

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client

from apps.knowledge.models import KnowledgeChunk, KnowledgeConflict, KnowledgeDocument, KnowledgeQueryTrace, MediaAsset


def _document(**overrides):
    defaults = {
        'name': 'demo.pdf', 'document_hash': hashlib.sha256(b'api-demo').hexdigest(),
        'path': 'knowledge/demo.pdf', 'page_count': 2,
        'embedding_model': 'tfidf:char-1-3:2048:v1', 'embedding_revision': 'v1',
        'embedding_dimension': 8, 'index_version': 'idx', 'collection_name': 'course-idx',
        'source_type': 'pdf', 'authority_level': 1, 'ingestion_status': 'ready',
        'latest_index_version': '', 'parser_name': 'pypdf',
    }
    defaults.update(overrides)
    return KnowledgeDocument.objects.create(**defaults)


def _chunks(document):
    parent = KnowledgeChunk.objects.create(
        document=document, chunk_id='parent-1', chapter='第三章', section='队列', page_number=1,
        content='父块：循环队列使用数组存储。' * 20, chunk_type='parent', heading_path='第三章 > 队列',
        char_start=0, char_end=300, token_count=300, content_hash='p' * 64,
    )
    child = KnowledgeChunk.objects.create(
        document=document, chunk_id='child-1', chapter='第三章', section='队列', page_number=1,
        content='循环队列判满条件是 (rear+1)%maxsize == front。', chunk_type='child',
        parent_chunk=parent, heading_path='第三章 > 队列', char_start=10, char_end=60,
        token_count=20, content_hash=hashlib.sha256('循环队列判满条件是 (rear+1)%maxsize == front。'.encode()).hexdigest(),
    )
    return parent, child


def _staff():
    return get_user_model().objects.create_user('staff-user', password='test-password', is_staff=True)


def _student(name='student-user'):
    return get_user_model().objects.create_user(name, password='test-password')


@pytest.mark.django_db
def test_tree_and_document_detail_are_read_only_for_students(client):
    document = _document()
    parent, child = _chunks(document)
    user = _student()
    client.force_login(user)
    response = client.get('/api/v1/knowledge/tree/')
    assert response.status_code == 200
    payload = response.json()['data']
    assert payload['documents'][0]['id'] == document.pk
    assert payload['documents'][0]['parents'][0]['chunk_id'] == parent.chunk_id
    assert payload['documents'][0]['parents'][0]['children'][0]['chunk_id'] == child.chunk_id
    detail = client.get(f'/api/v1/knowledge/documents/{document.pk}/')
    assert detail.status_code == 200
    assert detail.json()['data']['child_count'] == 1
    chunk = client.get(f'/api/v1/knowledge/chunks/{child.chunk_id}/')
    assert chunk.status_code == 200
    assert chunk.json()['data']['evidence']['chunk_id'] == child.chunk_id


@pytest.mark.django_db
def test_students_cannot_mutate_chunks_or_upload(client, settings, tmp_path):
    settings.EVIDENCE_RAG_UPLOAD_DIR = tmp_path / 'uploads'
    document = _document()
    _parent, child = _chunks(document)
    client.force_login(_student('read-only-student'))
    patch = client.generic('PATCH', f'/api/v1/knowledge/chunks/{child.chunk_id}/',
                           data='{"content":"篡改内容"}', content_type='application/json')
    assert patch.status_code == 403
    delete = client.delete(f'/api/v1/knowledge/chunks/{child.chunk_id}/')
    assert delete.status_code == 403
    upload = client.post('/api/v1/knowledge/documents/upload/',
                         {'file': SimpleUploadedFile('note.txt', b'hello', content_type='text/plain')})
    assert upload.status_code == 403
    reindex = client.post(f'/api/v1/knowledge/documents/{document.pk}/reindex/', data='{}', content_type='application/json')
    assert reindex.status_code == 403


@pytest.mark.django_db
def test_staff_can_patch_delete_and_restore_chunk(client):
    document = _document()
    _parent, child = _chunks(document)
    client.force_login(_staff())
    response = client.generic('PATCH', f'/api/v1/knowledge/chunks/{child.chunk_id}/',
                              data='{"content":"更新后的循环队列判满条件。"}', content_type='application/json')
    assert response.status_code == 200, response.content
    data = response.json()['data']
    assert data['content'] == '更新后的循环队列判满条件。'
    assert data['content_hash'] == hashlib.sha256('更新后的循环队列判满条件。'.encode()).hexdigest()
    assert data['token_count'] > 0

    deleted = client.delete(f'/api/v1/knowledge/chunks/{child.chunk_id}/')
    assert deleted.status_code == 200
    assert deleted.json()['data']['is_active'] is False
    child.refresh_from_db()
    assert child.is_active is False and child.deleted_at is not None

    restored = client.post(f'/api/v1/knowledge/chunks/{child.chunk_id}/restore/')
    assert restored.status_code == 200
    child.refresh_from_db()
    assert child.is_active is True and child.deleted_at is None


@pytest.mark.django_db
def test_staff_can_correct_child_parent_relationship(client):
    document = _document()
    first_parent, child = _chunks(document)
    second_parent = KnowledgeChunk.objects.create(
        document=document, chunk_id='parent-2', chapter='第四章', section='树', page_number=2,
        content='另一个父块。' * 20, chunk_type='parent', heading_path='第四章',
    )
    client.force_login(_staff())
    response = client.generic('PATCH', f'/api/v1/knowledge/chunks/{child.chunk_id}/',
                              data='{"parent_chunk_id":"%s"}' % second_parent.chunk_id,
                              content_type='application/json')
    assert response.status_code == 200
    assert response.json()['data']['parent_chunk_id'] == 'parent-2'
    child.refresh_from_db()
    assert child.parent_chunk_id == second_parent.pk

    other_document = _document(document_hash=hashlib.sha256(b'other-doc').hexdigest(), name='other.pdf')
    foreign_parent = KnowledgeChunk.objects.create(
        document=other_document, chunk_id='foreign-parent', chapter='第一章', section='外文', page_number=1,
        content='其他文档父块。', chunk_type='parent',
    )
    invalid = client.generic('PATCH', f'/api/v1/knowledge/chunks/{child.chunk_id}/',
                             data='{"parent_chunk_id":"%s"}' % foreign_parent.chunk_id,
                             content_type='application/json')
    assert invalid.status_code == 400
    parent_change = client.generic('PATCH', f'/api/v1/knowledge/chunks/{first_parent.chunk_id}/',
                                   data='{"parent_chunk_id":"%s"}' % second_parent.chunk_id,
                                   content_type='application/json')
    assert parent_change.status_code == 400


@pytest.mark.django_db
def test_csrf_is_enforced_for_mutations(settings, tmp_path):
    settings.EVIDENCE_RAG_UPLOAD_DIR = tmp_path / 'uploads'
    document = _document()
    _parent, child = _chunks(document)
    client = Client(enforce_csrf_checks=True)
    client.force_login(_staff())
    page = client.get('/knowledge/')
    assert page.status_code == 200
    token = client.cookies['csrftoken'].value
    without = client.post(f'/api/v1/knowledge/chunks/{child.chunk_id}/restore/')
    assert without.status_code == 403
    with_token = client.post(f'/api/v1/knowledge/chunks/{child.chunk_id}/restore/', HTTP_X_CSRFTOKEN=token)
    assert with_token.status_code == 200


@pytest.mark.django_db
def test_upload_requires_staff_and_persists_file(client, settings, tmp_path, monkeypatch):
    settings.EVIDENCE_RAG_UPLOAD_DIR = tmp_path / 'uploads'
    document = _document(name='上传讲义.txt', source_type='text', ingestion_status='ready')
    calls = {}

    def fake_ingest(path, annotation='', caption='', rebuild=True, index=True):
        calls['path'] = path
        calls['annotation'] = annotation
        return {'document': document, 'parsed': {'parents': 1, 'children': 2, 'warnings': []},
                'index': {'index_version': 'adv-x', 'collection_name': 'ev-adv-x'}, 'warning': ''}

    monkeypatch.setattr('apps.knowledge.services.advanced_index_service.ingest_advanced', fake_ingest)
    client.force_login(_staff())
    response = client.post('/api/v1/knowledge/documents/upload/', {
        'file': SimpleUploadedFile('讲义.txt', '循环队列判满条件'.encode('utf-8'), content_type='text/plain'),
        'annotation': '教师上传',
    })
    assert response.status_code == 200, response.content
    payload = response.json()['data']
    assert payload['status'] == 'ready'
    assert calls['annotation'] == '教师上传'
    assert calls['path'].is_file()
    assert calls['path'].read_text(encoding='utf-8') == '循环队列判满条件'


@pytest.mark.django_db
def test_upload_rejects_large_and_unsupported_files(client, settings, tmp_path):
    settings.EVIDENCE_RAG_UPLOAD_DIR = tmp_path / 'uploads'
    settings.EVIDENCE_RAG_MAX_UPLOAD_BYTES = 4
    client.force_login(_staff())
    large = client.post('/api/v1/knowledge/documents/upload/', {
        'file': SimpleUploadedFile('note.txt', b'12345', content_type='text/plain'),
    })
    assert large.status_code == 400
    unsupported = client.post('/api/v1/knowledge/documents/upload/', {
        'file': SimpleUploadedFile('note.xyz', b'123', content_type='application/octet-stream'),
    })
    assert unsupported.status_code == 400


@pytest.mark.django_db
def test_trace_and_conflict_access_is_owner_or_staff(client):
    owner = _student('trace-owner')
    other = _student('trace-other')
    staff = _staff()
    trace = KnowledgeQueryTrace.objects.create(trace_id='trace-1', user=owner, original_query='循环队列', retrieval_mode='advanced')
    client.force_login(owner)
    assert client.get('/api/v1/knowledge/traces/trace-1/').status_code == 200
    client.force_login(other)
    assert client.get('/api/v1/knowledge/traces/trace-1/').status_code == 403
    client.force_login(staff)
    assert client.get('/api/v1/knowledge/traces/trace-1/').status_code == 200


@pytest.mark.django_db
def test_knowledge_page_hides_admin_maintenance_from_students(client):
    student = _student('ui-student')
    client.force_login(student)
    page = client.get('/knowledge/').content.decode()
    assert '高级检索' in page
    assert '管理员维护' not in page
    client.force_login(_staff())
    staff_page = client.get('/knowledge/').content.decode()
    assert '管理员维护' in staff_page
    assert 'evidence-rag.css' in staff_page


@pytest.mark.django_db
def test_media_file_is_served_for_authenticated_users_only(client, settings, tmp_path):
    settings.BASE_DIR = tmp_path
    media_path = tmp_path / 'evidence' / 'queue.png'
    media_path.parent.mkdir(parents=True)
    media_path.write_bytes(b'\x89PNG\r\n\x1a\nfake')
    document = _document(source_type='image')
    asset = MediaAsset.objects.create(
        asset_id='image-1', document=document, modality='image', file_path='evidence/queue.png',
        mime_type='image/png', sha256='a' * 64, manual_annotation='循环队列图',
    )
    assert client.get('/api/v1/knowledge/media/image-1/file/').status_code == 401
    client.force_login(_student('media-reader'))
    response = client.get('/api/v1/knowledge/media/image-1/file/')
    assert response.status_code == 200
    assert response['Content-Type'] == 'image/png'
    assert response.streaming
    asset.file_path = '../outside.png'
    asset.save(update_fields=['file_path'])
    assert client.get('/api/v1/knowledge/media/image-1/file/').status_code == 404
