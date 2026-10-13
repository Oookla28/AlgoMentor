from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from core.http import api_endpoint, json_body
from core.exceptions import ValidationError, AuthenticationError
from .models import Problem, Submission
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
