import json

import pytest
from django.contrib.auth import get_user_model
from django.test import Client

from apps.knowledge.models import KnowledgeDocument
from apps.platform.models import AgentRun
from apps.workspace.models import TaskArtifact, Workspace, WorkspaceDocument


@pytest.fixture
def api_users(db):
    User = get_user_model()
    owner = User.objects.create_user('api-owner', password='x')
    other = User.objects.create_user('api-other', password='x')
    return owner, other


def json_post(client, url, payload):
    return client.post(url, data=json.dumps(payload), content_type='application/json')


@pytest.mark.django_db
def test_workbench_page_and_workspace_api(api_users):
    owner, _other = api_users
    client = Client()
    client.force_login(owner)
    page = client.get('/workbench/')
    assert page.status_code == 200
    assert 'Evidence 工作台' in page.content.decode('utf-8')
    workspaces = client.get('/api/v1/workbench/workspaces/').json()
    assert workspaces['success'] is True
    created = json_post(client, '/api/v1/workbench/workspaces/', {
        'name': '文献阅读', 'domain_pack_id': 'research_literature',
    }).json()
    assert created['success'] is True
    assert created['data']['name'] == '文献阅读'
    assert created['data']['visibility'] == 'private'


@pytest.mark.django_db
def test_task_api_accepts_and_other_user_cannot_read(api_users):
    owner, other = api_users
    workspace = Workspace.objects.create(name='私有', owner=owner, domain_pack_id='generic')
    document = KnowledgeDocument.objects.create(
        name='note.md', document_hash='hash-api', path='note.md', page_count=1,
        embedding_model='tfidf', embedding_revision='', embedding_dimension=0,
        index_version='', collection_name='',
    )
    WorkspaceDocument.objects.create(workspace=workspace, document=document, status='ready')
    client = Client()
    client.force_login(owner)
    response = json_post(client, '/api/v1/workbench/tasks/', {
        'workspace_id': workspace.pk, 'task_type': 'grounded_qa', 'query': '资料里说了什么？',
    })
    payload = response.json()
    assert response.status_code == 200
    assert payload['success'] is True
    run_id = payload['data']['run_id']
    assert payload['data']['status'] == 'QUEUED'

    other_client = Client()
    other_client.force_login(other)
    denied = other_client.get(f'/api/v1/workbench/tasks/{run_id}/')
    assert denied.status_code == 403
    denied_workspace = other_client.get(f'/api/v1/workbench/workspaces/{workspace.pk}/')
    assert denied_workspace.status_code == 403


@pytest.mark.django_db
def test_artifact_download_is_workspace_scoped(api_users):
    owner, other = api_users
    workspace = Workspace.objects.create(name='私有', owner=owner, domain_pack_id='generic')
    run = AgentRun.objects.create(
        run_id='artifact-run', user=owner, workspace=workspace, query='test', status='SUCCEEDED',
    )
    artifact = TaskArtifact.objects.create(
        run=run, kind='comparison', format='markdown', filename='result.md', content='# 结果\n\n来源证据',
    )
    owner_client = Client()
    owner_client.force_login(owner)
    allowed = owner_client.get(f'/workbench/artifacts/{artifact.artifact_id}/download/')
    assert allowed.status_code == 200
    assert 'attachment' in allowed['Content-Disposition']
    assert '来源证据' in allowed.content.decode('utf-8')

    other_client = Client()
    other_client.force_login(other)
    denied = other_client.get(f'/workbench/artifacts/{artifact.artifact_id}/download/')
    assert denied.status_code == 403


@pytest.mark.django_db
def test_private_source_page_is_not_readable_by_another_user(api_users):
    from apps.knowledge.models import KnowledgeChunk
    owner, other = api_users
    workspace = Workspace.objects.create(name='私有来源', owner=owner, domain_pack_id='generic')
    document = KnowledgeDocument.objects.create(
        name='private.md', document_hash='hash-source', path='private.md', page_count=1,
        embedding_model='tfidf', embedding_revision='', embedding_dimension=0,
        index_version='', collection_name='',
    )
    chunk = KnowledgeChunk.objects.create(
        document=document, chunk_id='private-chunk', chapter='', section='',
        page_number=1, content='私有资料内容', chunk_type='child',
    )
    WorkspaceDocument.objects.create(workspace=workspace, document=document, status='ready')
    owner_client = Client()
    owner_client.force_login(owner)
    assert owner_client.get(f'/knowledge/source/{chunk.chunk_id}/').status_code == 200
    other_client = Client()
    other_client.force_login(other)
    assert other_client.get(f'/knowledge/source/{chunk.chunk_id}/').status_code == 403


@pytest.mark.django_db
def test_shared_workspace_is_readable_but_upload_is_rejected(api_users):
    _owner, learner = api_users
    User = get_user_model()
    teacher = User.objects.create_user('teacher', password='x', is_staff=True)
    shared = Workspace.objects.create(name='共享课程', owner=teacher, visibility='shared', domain_pack_id='data_structures')
    client = Client()
    client.force_login(learner)
    detail = client.get(f'/api/v1/workbench/workspaces/{shared.pk}/').json()
    assert detail['success'] is True
    assert detail['data']['can_write'] is False
    from django.core.files.uploadedfile import SimpleUploadedFile
    upload = client.post(
        f'/api/v1/workbench/workspaces/{shared.pk}/documents/',
        {'file': SimpleUploadedFile('note.txt', b'hello', content_type='text/plain')},
    )
    assert upload.status_code == 403
    assert upload.json()['error']['code'] == 'WORKSPACE_READ_ONLY'
