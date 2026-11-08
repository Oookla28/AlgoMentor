"""Server-side workspace authorization.

Skills, prompts, documents and model output never grant access. Every read and
write goes through these helpers, and staff do not receive an implicit bypass to
another learner's private space.
"""

from core.exceptions import BusinessError
from core.security.permissions import require_user

from .models import Workspace, WorkspaceMember


def _membership(user, workspace):
    if not user or not user.is_authenticated:
        return None
    return WorkspaceMember.objects.filter(workspace=workspace, user=user).first()


def can_read(user, workspace) -> bool:
    require_user(user)
    if workspace.owner_id == user.pk:
        return True
    if _membership(user, workspace) is not None:
        return True
    return workspace.visibility == 'shared' and not workspace.is_archived


def can_write(user, workspace) -> bool:
    require_user(user)
    if workspace.owner_id == user.pk:
        return True
    membership = _membership(user, workspace)
    if membership is not None and membership.role == 'editor':
        return True
    return bool(user.is_staff and workspace.visibility == 'shared')


def can_manage(user, workspace) -> bool:
    require_user(user)
    return workspace.owner_id == user.pk or (user.is_staff and workspace.visibility == 'shared')


def readable_workspaces(user):
    require_user(user)
    shared = Workspace.objects.filter(visibility='shared', is_archived=False)
    owned = Workspace.objects.filter(owner=user)
    member_ids = WorkspaceMember.objects.filter(user=user).values_list('workspace_id', flat=True)
    member = Workspace.objects.filter(pk__in=member_ids)
    return (shared | owned | member).distinct()


def ensure_readable(user, workspace) -> Workspace:
    if workspace is None or not can_read(user, workspace):
        raise BusinessError('无权访问该工作空间。', code='WORKSPACE_PERMISSION_DENIED', status_code=403)
    return workspace


def ensure_writable(user, workspace) -> Workspace:
    if workspace is None or not can_write(user, workspace):
        raise BusinessError('当前空间仅可阅读，不能上传或修改资料。', code='WORKSPACE_READ_ONLY', status_code=403)
    return workspace


def ensure_manage(user, workspace) -> Workspace:
    if workspace is None or not can_manage(user, workspace):
        raise BusinessError('只有空间所有者或管理员可以执行该操作。', code='WORKSPACE_MANAGE_DENIED', status_code=403)
    return workspace
