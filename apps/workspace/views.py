"""Workbench page, machine-readable APIs and artifact downloads."""

from pathlib import Path

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone

from core.exceptions import BusinessError, ValidationError
from core.http import api_endpoint, json_body
from core.security.permissions import require_user

from apps.platform.capabilities import probe_capabilities
from apps.platform.domains import list_domain_packs, list_task_packs
from apps.platform.models import AgentRun
from apps.platform.skills import skills_health

from .models import TaskArtifact, Workspace
from .permissions import can_manage, can_read, ensure_readable
from .services.documents import remove_document, restore_document, retry_document, upload_document
from .services.literature import recommend_for_workspace
from .services.tasks import (
    ACTIVE_STATUSES, cancel_task, create_task, retry_task, serialize_task,
    submit_feedback, worker_status,
)
from .services.workspaces import (
    ensure_personal_workspace, serialize_document_link, serialize_workspace,
)


def _workspace(user, workspace_id):
    workspace = Workspace.objects.select_related('owner').filter(pk=workspace_id).first()
    if workspace is None:
        raise BusinessError('工作空间不存在。', code='WORKSPACE_NOT_FOUND', status_code=404)
    return ensure_readable(user, workspace)


def _task_for_user(user, run_id):
    run = AgentRun.objects.select_related('workspace').filter(run_id=run_id).first()
    if run is None:
        raise BusinessError('任务不存在。', code='TASK_NOT_FOUND', status_code=404)
    allowed = run.user_id == user.pk or (run.workspace_id and can_manage(user, run.workspace))
    if not allowed:
        raise BusinessError('无权查看该任务。', code='TASK_PERMISSION_DENIED', status_code=403)
    return run


VIEW_MODES = {
    'overview': ('workbench', 'Evidence 工作台'),
    'spaces': ('workbench-spaces', '我的空间'),
    'literature': ('workbench-literature', '文献库'),
    'code': ('workbench-code', '代码分析'),
}


@login_required
def workbench(request):
    require_user(request.user)
    ensure_personal_workspace(request.user)
    view_mode = request.GET.get('view') or 'overview'
    if view_mode not in VIEW_MODES:
        view_mode = 'overview'
    page_name, page_title = VIEW_MODES[view_mode]
    workspaces = [
        serialize_workspace(request.user, workspace)
        for workspace in _visible_workspaces(request.user)
    ]
    selected = None
    requested = request.GET.get('workspace')
    if requested:
        selected = next((row for row in workspaces if str(row['id']) == str(requested)), None)
    if selected is None and view_mode in ('literature', 'code'):
        domain = 'research_literature' if view_mode == 'literature' else 'software_engineering'
        selected = next((row for row in workspaces if row['domain_pack_id'] == domain), None)
    selected = selected or (workspaces[0] if workspaces else None)
    selected_obj = Workspace.objects.filter(pk=selected['id']).first() if selected else None
    if selected_obj is not None:
        selected = serialize_workspace(request.user, selected_obj, include_documents=True)
    tasks = []
    if selected_obj is not None:
        tasks = [
            serialize_task(run, staff=request.user.is_staff)
            for run in AgentRun.objects.filter(user=request.user, workspace=selected_obj).order_by('-created_at')[:12]
        ]
    capabilities = {entry['name']: entry for entry in probe_capabilities()}
    task_types = []
    if selected_obj is not None:
        task_types = [
            {'task_id': task.task_id, 'name': task.name, 'description': task.description,
             'domain_pack_id': task.domain_pack_id}
            for task in list_task_packs(selected_obj.domain_pack_id)
            if task.task_id in ('grounded_qa', 'guided_learning', 'paper_comparison', 'code_investigation')
        ]
    literature_workspaces = [row for row in workspaces if row['domain_pack_id'] == 'research_literature']
    code_workspaces = [row for row in workspaces if row['domain_pack_id'] == 'software_engineering']
    my_spaces = [
        row for row in workspaces
        if row['visibility'] == 'private' and row['owner'] == request.user.username
    ]
    shared_spaces = [row for row in workspaces if row['visibility'] == 'shared']
    literature = None
    if view_mode == 'literature' and selected_obj is not None:
        literature = recommend_for_workspace(request.user, selected_obj, limit=6)
    return render(request, 'workbench/index.html', {
        'page_title': page_title,
        'workbench_view': view_mode,
        'page_name': page_name,
        'workspaces': workspaces,
        'selected_workspace': selected,
        'initial_tasks': tasks,
        'task_types': task_types,
        'domain_packs': [pack.to_dict() for pack in list_domain_packs()],
        'literature_workspaces': literature_workspaces,
        'code_workspaces': code_workspaces,
        'my_spaces': my_spaces,
        'shared_spaces': shared_spaces,
        'literature': literature,
        'worker': worker_status(),
        'capabilities': capabilities,
        'skills': skills_health(),
        'active_statuses': ACTIVE_STATUSES,
    })


def _visible_workspaces(user):
    from .permissions import readable_workspaces
    return readable_workspaces(user).select_related('owner').order_by('-visibility', '-updated_at')[:30]


@api_endpoint(methods=('GET', 'POST'))
def workspaces_api(request):
    if request.method == 'POST':
        body = json_body(request)
        from .services.workspaces import create_workspace
        workspace = create_workspace(
            request.user, body.get('name'), body.get('domain_pack_id', 'generic'),
            description=body.get('description', ''),
            visibility=body.get('visibility', 'private'),
        )
        return serialize_workspace(request.user, workspace, include_documents=True)
    return {'workspaces': [serialize_workspace(request.user, workspace) for workspace in _visible_workspaces(request.user)]}


@api_endpoint()
def workspace_detail_api(request, workspace_id):
    workspace = _workspace(request.user, workspace_id)
    payload = serialize_workspace(request.user, workspace, include_documents=True)
    payload['tasks'] = [
        serialize_task(run, staff=request.user.is_staff)
        for run in AgentRun.objects.filter(user=request.user, workspace=workspace).order_by('-created_at')[:20]
    ]
    return payload


@api_endpoint(methods=('POST',))
def upload_document_api(request, workspace_id):
    workspace = _workspace(request.user, workspace_id)
    uploaded = request.FILES.get('file')
    annotation = (request.POST.get('annotation') or '').strip()[:20000]
    link = upload_document(request.user, workspace, uploaded, annotation=annotation)
    return {
        'document': serialize_document_link(link),
        'workspace': serialize_workspace(request.user, workspace),
    }


@api_endpoint(methods=('POST',))
def document_action_api(request, workspace_id, document_id):
    from .models import WorkspaceDocument
    workspace = _workspace(request.user, workspace_id)
    link = WorkspaceDocument.objects.filter(pk=document_id, workspace=workspace).first()
    if link is None:
        raise BusinessError('资料不存在。', code='DOCUMENT_NOT_FOUND', status_code=404)
    body = json_body(request)
    action = str(body.get('action') or '').strip()
    if action == 'remove':
        payload = remove_document(request.user, workspace, link)
    elif action == 'restore':
        payload = restore_document(request.user, workspace, link)
    elif action == 'retry':
        link = retry_document(request.user, workspace, link)
        payload = serialize_document_link(link)
    else:
        raise ValidationError('未知的资料操作。', code='DOCUMENT_ACTION_INVALID')
    return {'document': payload, 'workspace': serialize_workspace(request.user, workspace)}


@api_endpoint(methods=('GET', 'POST'))
def tasks_api(request):
    if request.method == 'POST':
        body = json_body(request)
        workspace = _workspace(request.user, body.get('workspace_id'))
        run = create_task(
            request.user, workspace, str(body.get('task_type') or 'grounded_qa').strip(),
            body.get('query'), requested_mode=str(body.get('requested_mode') or 'standard'),
        )
        return serialize_task(run, staff=request.user.is_staff)
    workspace_id = request.GET.get('workspace_id')
    queryset = AgentRun.objects.filter(user=request.user).select_related('workspace')
    if workspace_id:
        workspace = _workspace(request.user, workspace_id)
        queryset = queryset.filter(workspace=workspace)
    return {'tasks': [serialize_task(run, staff=request.user.is_staff) for run in queryset.order_by('-created_at')[:30]]}


@api_endpoint()
def task_detail_api(request, run_id):
    run = _task_for_user(request.user, run_id)
    return serialize_task(run, include_steps=True, staff=request.user.is_staff)


@api_endpoint(methods=('POST',))
def task_action_api(request, run_id):
    run = _task_for_user(request.user, run_id)
    body = json_body(request)
    action = str(body.get('action') or '').strip()
    if action == 'cancel':
        return serialize_task(cancel_task(request.user, run), staff=request.user.is_staff)
    if action == 'retry':
        new_run = retry_task(request.user, run)
        return serialize_task(new_run, staff=request.user.is_staff)
    if action == 'feedback':
        row = submit_feedback(request.user, run, body.get('rating'), body.get('comment', ''))
        return {'rating': row.rating, 'comment': row.comment}
    raise ValidationError('未知的任务操作。', code='TASK_ACTION_INVALID')


@api_endpoint()
def literature_recommendations_api(request):
    workspace = _workspace(request.user, request.GET.get('workspace_id'))
    try:
        limit = int(request.GET.get('limit') or 6)
    except (TypeError, ValueError):
        limit = 6
    return recommend_for_workspace(request.user, workspace, limit=limit)


@api_endpoint()
def status_api(request):
    return {
        'worker': worker_status(),
        'skills': skills_health(),
        'capabilities': probe_capabilities(),
        'generated_at': timezone.now().isoformat(),
        'domain_packs': [pack.to_dict() for pack in list_domain_packs()],
    }


@login_required
def artifact_download(request, artifact_id):
    require_user(request.user)
    artifact = get_object_or_404(TaskArtifact.objects.select_related('run__workspace'), artifact_id=artifact_id)
    run = artifact.run
    allowed = run.user_id == request.user.pk or (run.workspace_id and can_read(request.user, run.workspace))
    if not allowed:
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied('无权下载该产物。')
    suffix = Path(artifact.filename).suffix.lower()
    content_type = {
        '.html': 'text/html; charset=utf-8', '.md': 'text/markdown; charset=utf-8',
        '.diff': 'text/plain; charset=utf-8', '.patch': 'text/plain; charset=utf-8',
    }.get(suffix, 'text/plain; charset=utf-8')
    response = HttpResponse(artifact.content, content_type=content_type)
    filename = Path(artifact.filename).name or 'artifact.txt'
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    response['X-Content-Type-Options'] = 'nosniff'
    return response
