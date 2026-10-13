from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.cache import never_cache
from django.core.exceptions import RequestDataTooBig
from core.http import api_endpoint, json_body
from core.exceptions import ValidationError, AuthenticationError
from .models import Problem, Submission, CodeDraft
from .services.problem_service import problem_queryset
from .services.submission_service import run_code, submit_code, serialize_submission


@login_required
def problem_list(request):
    return render(request, "problems/list.html", {"problems": problem_queryset(request.GET.get("difficulty"), request.GET.get("point"), request.GET.get("chapter"), request.GET.get("q")), "selected_difficulty": request.GET.get("difficulty", ""), "selected_point": request.GET.get("point", "")})


@login_required
def problem_detail(request, slug):
    problem = get_object_or_404(Problem, slug=slug, is_active=True)
    return render(request, "problems/detail.html", {"problem": problem, "submissions": Submission.objects.filter(user=request.user, problem=problem)[:10],
        "solved": Submission.objects.filter(user=request.user, problem=problem, status="ACCEPTED").exists()})


@login_required
def lab(request):
    return render(request, "problems/lab.html", {"problems": problem_queryset()})


@api_endpoint(methods=("POST",))
def code_run(request):
    data = json_body(request)
    return run_code(request.user, data.get("code", ""), data.get("stdin", "")).to_dict()


@api_endpoint(methods=("POST",))
def code_submit(request):
    data = json_body(request)
    try:
        problem_id = int(data.get("problem_id", ""))
    except (TypeError, ValueError) as exc:
        raise ValidationError("请选择题目。") from exc
    submission = submit_code(request.user, problem_id, data.get("code", ""), data.get("hints_used", 0), data.get("duration_seconds", 0), data.get("request_key"))
    return serialize_submission(submission)


@api_endpoint()
def submission_detail(request, submission_id):
    submission = Submission.objects.get(pk=submission_id, user=request.user)
    return serialize_submission(submission)


@api_endpoint()
def reference_solution(request, problem_id):
    problem = Problem.objects.get(pk=problem_id, is_active=True)
    if not Submission.objects.filter(user=request.user, problem=problem, status="ACCEPTED").exists():
        raise AuthenticationError("独立通过后可查看参考代码。先使用分层提示继续尝试。", code="REFERENCE_LOCKED", status_code=403)
    return {"code": problem.reference_solution, "complexity": problem.reference_complexity}


@api_endpoint(methods=("POST",))
def diagnosis_api(request, submission_id):
    from .services.diagnosis_service import diagnose_with_ai
    data = json_body(request)
    return diagnose_with_ai(request.user, submission_id, data.get("level", 1))


@never_cache
@api_endpoint(methods=("GET", "POST"))
def code_draft(request):
    try:
        data = json_body(request) if request.method == "POST" else request.GET
    except RequestDataTooBig:
        raise ValidationError("草稿请求过大，请缩短代码或标准输入。")
    identifier = data.get("problem_id")
    problem = None
    if identifier not in (None, ""):
        if isinstance(identifier, bool) or not str(identifier).isdigit() or int(identifier) < 1:
            raise ValidationError("请选择有效题目。")
        try:
            problem = Problem.objects.get(pk=int(identifier), is_active=True)
        except (ValueError, TypeError):
            raise ValidationError("请选择有效题目。")
    scope = f"problem:{problem.pk}" if problem else "lab"
    if request.method == "POST":
        code, stdin = data.get("code", ""), data.get("stdin", "")
        if not isinstance(code, str) or len(code.encode("utf-8")) > 64000:
            raise ValidationError("代码草稿须为文本，最多 64 KB。")
        if not isinstance(stdin, str) or len(stdin.encode("utf-8")) > 32000:
            raise ValidationError("输入草稿须为文本，最多 32 KB。")
        draft, _ = CodeDraft.objects.update_or_create(user=request.user, scope=scope, defaults={"problem": problem, "code": code, "stdin": stdin})
    else:
        draft = CodeDraft.objects.filter(user=request.user, scope=scope).first()
    return {"saved": draft is not None, "scope": scope, "problem_id": problem.pk if problem else None,
            "code": draft.code if draft else "", "stdin": draft.stdin if draft else "",
            "updated_at": draft.updated_at.isoformat() if draft else None,
            "message": "草稿只保存在当前账号，不会运行、提交评测或更新掌握度。"}
