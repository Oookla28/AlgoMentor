"""Workspace lifecycle helpers shared by views, seed commands and tests."""

from django.db import transaction

from core.exceptions import BusinessError, ValidationError
from core.security.permissions import require_user

from apps.platform.domains import get_domain_pack

from ..models import Workspace, WorkspaceDocument, WorkspaceMember
from ..permissions import can_read, can_write

DEFAULT_DOMAIN = 'generic'
COURSE_WORKSPACE_SLUG = 'shared-course-data-structures'


def create_workspace(user, name, domain_pack_id=DEFAULT_DOMAIN, description='', visibility='private'):
    require_user(user)
    name = (name or '').strip()
    if not name or len(name) > 120:
        raise ValidationError('工作空间名称须为 1 至 120 字。')
    pack = get_domain_pack(domain_pack_id)
    if pack is None:
        raise ValidationError('未知的领域知识包。', code='DOMAIN_PACK_NOT_FOUND')
    visibility = (visibility or 'private').strip()
    if visibility not in ('private', 'shared'):
        raise ValidationError('工作空间可见性无效。')
    if visibility == 'shared' and not user.is_staff:
        raise BusinessError('共享空间只能由管理员创建。', code='SHARED_WORKSPACE_STAFF_ONLY', status_code=403)
    with transaction.atomic():
        workspace = Workspace.objects.create(
            name=name,
            description=(description or '').strip()[:2000],
            owner=user,
            visibility=visibility,
            domain_pack_id=pack.pack_id,
        )
        WorkspaceMember.objects.get_or_create(workspace=workspace, user=user, defaults={'role': 'editor'})
    return workspace


def ensure_personal_workspace(user):
    """Create a private default space on first visit; never reuse another user's space."""
    require_user(user)
    existing = Workspace.objects.filter(owner=user, visibility='private', is_archived=False).order_by('created_at').first()
    if existing is not None:
        return existing
    return create_workspace(user, '我的学习空间', domain_pack_id=DEFAULT_DOMAIN)


def ensure_shared_course_workspace():
    """Create/link the read-only compatibility course space when a staff owner exists."""
    from django.contrib.auth import get_user_model
    from apps.knowledge.models import KnowledgeDocument

    workspace = Workspace.objects.filter(slug=COURSE_WORKSPACE_SLUG).first()
    if workspace is None:
        User = get_user_model()
        owner = User.objects.filter(is_staff=True, is_active=True).order_by('pk').first()
        if owner is None:
            return None
        workspace = Workspace.objects.create(
            name='数据结构共享课程空间',
            slug=COURSE_WORKSPACE_SLUG,
            description='由教师/管理员维护的共享课程资料；所有学习者可阅读，不能自行修改。',
            owner=owner,
            visibility='shared',
            domain_pack_id='data_structures',
        )
    linked = 0
    for document in KnowledgeDocument.objects.all():
        if WorkspaceDocument.objects.filter(document=document).exists():
            continue
        status = 'ready' if document.ingestion_status in ('ready', 'parsed', 'legacy') else 'partial'
        WorkspaceDocument.objects.create(
            workspace=workspace, document=document, added_by=workspace.owner,
            original_name=document.name, status=status,
            file_path=document.path,
        )
        linked += 1
    return workspace, linked


def serialize_workspace(user, workspace, include_documents=False):
    document_counts = {}
    for row in WorkspaceDocument.objects.filter(workspace=workspace).values('status'):
        document_counts[row['status']] = document_counts.get(row['status'], 0) + 1
    payload = {
        'id': workspace.pk,
        'name': workspace.name,
        'description': workspace.description,
        'visibility': workspace.visibility,
        'domain_pack_id': workspace.domain_pack_id,
        'owner': workspace.owner.username if workspace.owner_id else '',
        'created_at': workspace.created_at.isoformat() if workspace.created_at else '',
        'updated_at': workspace.updated_at.isoformat() if workspace.updated_at else '',
        'can_write': can_write(user, workspace),
        'can_manage': workspace.owner_id == user.pk or (user.is_staff and workspace.visibility == 'shared'),
        'document_counts': document_counts,
    }
    if include_documents:
        payload['documents'] = [
            serialize_document_link(link) for link in workspace.documents.select_related('document').order_by('-created_at')
        ]
    return payload


def serialize_document_link(link):
    document = link.document
    return {
        'id': link.pk,
        'document_id': document.pk if document else None,
        'name': document.name if document else link.original_name,
        'status': link.status,
        'status_label': dict(WorkspaceDocument.STATUS).get(link.status, link.status),
        'error': link.error_message,
        'source_type': document.source_type if document else '',
        'page_count': document.page_count if document else 0,
        'ingestion_status': document.ingestion_status if document else '',
        'created_at': link.created_at.isoformat() if link.created_at else '',
        'removed_at': link.removed_at.isoformat() if link.removed_at else '',
    }


def workspace_membership_check(user, workspace):
    return can_read(user, workspace)
