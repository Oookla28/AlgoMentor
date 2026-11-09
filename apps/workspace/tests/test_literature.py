import json

import pytest
from django.contrib.auth import get_user_model
from django.test import Client

from apps.knowledge.models import KnowledgeChunk, KnowledgeDocument
from apps.workspace.models import Workspace, WorkspaceDocument
from apps.workspace.services.literature import recommend_for_workspace


def add_paper(workspace, user, name, content, seed):
    document = KnowledgeDocument.objects.create(
        name=name, document_hash=f'lit-{seed}', path=name, page_count=2,
        embedding_model='tfidf', embedding_revision='', embedding_dimension=2048,
        index_version='', collection_name='',
    )
    KnowledgeChunk.objects.create(
        document=document, chunk_id=f'lit-chunk-{seed}', chapter='论文', section=name,
        page_number=1, content=content, chunk_type='child',
    )
    WorkspaceDocument.objects.create(
        workspace=workspace, document=document, added_by=user, original_name=name, status='ready',
    )
    return document


@pytest.mark.django_db
def test_recommendations_use_catalog_and_only_own_private_library():
    User = get_user_model()
    owner = User.objects.create_user('lit-owner', password='x')
    other = User.objects.create_user('lit-other', password='x')
    workspace = Workspace.objects.create(name='我的论文', owner=owner, domain_pack_id='research_literature')
    add_paper(
        workspace, owner, 'sparse_attention.md',
        '# Sparse Attention for Long Documents\n\n'
        'We study sparse attention and long document retrieval with transformer models.',
        'a',
    )
    second = Workspace.objects.create(name='另一篇', owner=owner, domain_pack_id='research_literature')
    add_paper(
        second, owner, 'retrieval_notes.md',
        '# Retrieval and Attention\n\nDense retrieval with attention for long document question answering.',
        'b',
    )
    foreign = Workspace.objects.create(name='别人的空间', owner=other, domain_pack_id='research_literature')
    add_paper(
        foreign, other, 'secret.md',
        '# Secret Sparse Attention\n\nPrivate notes about sparse attention that must not leak.',
        'c',
    )
    result = recommend_for_workspace(owner, workspace)
    assert result['documents']
    assert result['recommendations']
    sources = {item['source'] for item in result['recommendations']}
    assert 'catalog' in sources
    assert 'user_library' in sources
    titles = ' '.join(item['title'] for item in result['recommendations'])
    assert 'Secret' not in titles
    assert all(item['reason_terms'] for item in result['recommendations'])
    catalog_titles = [item['title'] for item in result['recommendations'] if item['source'] == 'catalog']
    assert any('Longformer' in title or 'Sparse' in title or 'Retrieval' in title for title in catalog_titles)


@pytest.mark.django_db
def test_recommendations_api_is_workspace_scoped():
    User = get_user_model()
    owner = User.objects.create_user('lit-api-owner', password='x')
    other = User.objects.create_user('lit-api-other', password='x')
    workspace = Workspace.objects.create(name='论文库', owner=owner, domain_pack_id='research_literature')
    add_paper(workspace, owner, 'paper.md', '# Attention Retrieval\n\nTransformer attention and retrieval.', 'api')
    client = Client()
    client.force_login(owner)
    allowed = client.get(f'/api/v1/workbench/literature/recommendations/?workspace_id={workspace.pk}')
    payload = allowed.json()
    assert allowed.status_code == 200
    assert payload['success'] is True
    assert payload['data']['recommendations']
    other_client = Client()
    other_client.force_login(other)
    denied = other_client.get(f'/api/v1/workbench/literature/recommendations/?workspace_id={workspace.pk}')
    assert denied.status_code == 403


@pytest.mark.django_db
def test_workbench_views_and_sidebar_entries():
    User = get_user_model()
    user = User.objects.create_user('lit-view-user', password='x')
    research = Workspace.objects.create(name='文献空间', owner=user, domain_pack_id='research_literature')
    add_paper(research, user, 'attention.md', '# Attention Is Useful\n\nTransformer attention retrieval.', 'view')
    code = Workspace.objects.create(name='代码空间', owner=user, domain_pack_id='software_engineering')
    client = Client(HTTP_HOST='127.0.0.1')
    client.force_login(user)
    for view, workspace, marker in (
        ('spaces', research, '我的私有空间'),
        ('literature', research, '相关文献推荐'),
        ('code', code, '执行边界'),
        ('overview', research, '空间资料'),
    ):
        response = client.get(f'/workbench/?view={view}&workspace={workspace.pk}')
        assert response.status_code == 200
        html = response.content.decode('utf-8')
        assert marker in html
        assert '我的空间' in html and '文献库' in html and '代码分析' in html
    page = client.get('/workbench/?view=code&workspace=' + str(code.pk))
    assert '开始代码分析' in page.content.decode('utf-8')
