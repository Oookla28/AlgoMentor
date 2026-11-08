import pytest
from django.contrib.auth import get_user_model

from apps.workspace.models import Workspace, WorkspaceMember
from apps.workspace.permissions import can_manage, can_read, can_write, readable_workspaces
from apps.workspace.services.documents import active_document_ids
from apps.workspace.services.tasks import create_task


@pytest.fixture
def users(db):
    User = get_user_model()
    owner = User.objects.create_user('owner', password='x')
    other = User.objects.create_user('other', password='x')
    staff = User.objects.create_user('staff', password='x', is_staff=True)
    return owner, other, staff


@pytest.mark.django_db
def test_private_workspace_is_owner_only(users):
    owner, other, staff = users
    workspace = Workspace.objects.create(name='私有', owner=owner, domain_pack_id='generic')
    assert can_read(owner, workspace)
    assert can_write(owner, workspace)
    assert can_manage(owner, workspace)
    assert not can_read(other, workspace)
    assert not can_write(other, workspace)
    assert not can_read(staff, workspace)
    assert list(readable_workspaces(other)) == []


@pytest.mark.django_db
def test_shared_workspace_is_readable_but_not_writable_by_learners(users):
    _owner, other, staff = users
    workspace = Workspace.objects.create(name='共享', owner=staff, visibility='shared', domain_pack_id='data_structures')
    assert can_read(other, workspace)
    assert not can_write(other, workspace)
    assert not can_manage(other, workspace)
    assert can_write(staff, workspace)
    assert can_manage(staff, workspace)


@pytest.mark.django_db
def test_editor_membership_can_write_but_not_manage(users):
    owner, other, _staff = users
    workspace = Workspace.objects.create(name='协作', owner=owner, domain_pack_id='generic')
    WorkspaceMember.objects.create(workspace=workspace, user=other, role='editor')
    assert can_read(other, workspace)
    assert can_write(other, workspace)
    assert not can_manage(other, workspace)


@pytest.mark.django_db
def test_removed_documents_leave_the_retrieval_scope(users):
    from apps.knowledge.models import KnowledgeDocument
    from apps.workspace.models import WorkspaceDocument
    owner, _other, _staff = users
    workspace = Workspace.objects.create(name='资料', owner=owner, domain_pack_id='generic')
    document = KnowledgeDocument.objects.create(
        name='note.md', document_hash='hash-1', path='note.md', page_count=1,
        embedding_model='tfidf', embedding_revision='', embedding_dimension=0,
        index_version='', collection_name='',
    )
    link = WorkspaceDocument.objects.create(workspace=workspace, document=document, status='ready')
    assert active_document_ids(workspace) == [document.pk]
    link.status = 'removed'
    link.save(update_fields=['status'])
    assert active_document_ids(workspace) == []


@pytest.mark.django_db
def test_create_task_rejects_other_users_workspace(users):
    owner, other, _staff = users
    workspace = Workspace.objects.create(name='私有', owner=owner, domain_pack_id='generic')
    with pytest.raises(Exception) as captured:
        create_task(other, workspace, 'grounded_qa', '测试问题')
    assert getattr(captured.value, 'code', '') == 'WORKSPACE_PERMISSION_DENIED'


@pytest.mark.django_db
def test_create_task_requires_domain_pack_capability(users):
    owner, _other, _staff = users
    generic = Workspace.objects.create(name='通用', owner=owner, domain_pack_id='generic')
    with pytest.raises(Exception) as captured:
        create_task(owner, generic, 'paper_comparison', '比较两篇论文')
    assert getattr(captured.value, 'code', '') == 'TASK_PACK_NOT_AVAILABLE'
