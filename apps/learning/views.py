from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.utils.dateparse import parse_date
from core.http import api_endpoint, json_body
from core.exceptions import ValidationError
from apps.learning.models import MistakeRecord, LearningActivity, MasteryState
from .services.progress_service import get_learning_summary
from .services.recommendation_service import get_recommendations
from .services.mistake_service import review_mistake


@login_required
def overview(request):
    return render(request, "learning/overview.html", {"summary": get_learning_summary(request.user),
        "mastery_states": MasteryState.objects.filter(user=request.user).select_related("knowledge_point"),
        "recommendations": get_recommendations(request.user), "activities": LearningActivity.objects.filter(user=request.user).select_related("knowledge_point", "submission__problem")[:12]})


def filtered_mistakes(user, params):
    records = MistakeRecord.objects.filter(user=user).select_related("problem", "submission").prefetch_related("problem__knowledge_points")
    if params.get("resolved") in ("true", "false"):
        records = records.filter(resolved=params["resolved"] == "true")
    if params.get("error_type"):
        records = records.filter(error_type=params["error_type"])
    if str(params.get("chapter")) in ("1", "2", "3", "4"):
        records = records.filter(problem__knowledge_points__chapter=params["chapter"])
    if params.get("point"):
        records = records.filter(problem__knowledge_points__slug=params["point"])
    if params.get("since"):
        try:
            date = parse_date(params["since"])
        except ValueError as exc:
            raise ValidationError("筛选日期格式无效。") from exc
        if not date:
            raise ValidationError("筛选日期格式为 YYYY-MM-DD。")
        records = records.filter(created_at__date__gte=date)
    if params.get("max_mastery"):
        try:
            maximum = float(params["max_mastery"])
        except ValueError as exc:
            raise ValidationError("掌握指数应为数字。") from exc
        points = MasteryState.objects.filter(user=user, index__lte=maximum).values_list("knowledge_point_id", flat=True)
        records = records.filter(problem__knowledge_points__in=points)
    return records.distinct()


@login_required
def mistakes(request):
    return render(request, "learning/mistakes.html", {"mistakes": filtered_mistakes(request.user, request.GET), "filters": request.GET})


@api_endpoint()
def summary_api(request):
    try:
        days = int(request.GET.get("days", 7))
    except ValueError as exc:
        raise ValidationError("统计天数应为整数。") from exc
    return get_learning_summary(request.user, days)


@api_endpoint()
def mistakes_api(request):
    records = filtered_mistakes(request.user, request.GET)[:100]
    return {"mistakes": [{"id": item.pk, "problem_id": item.problem_id, "problem_slug": item.problem.slug, "title": item.problem.title,
              "error_type": item.error_type, "failure_reason": item.failure_reason, "ai_diagnosis": item.ai_diagnosis, "resolved": item.resolved,
              "created_at": item.created_at.isoformat(), "last_reviewed_at": item.last_reviewed_at.isoformat() if item.last_reviewed_at else None} for item in records]}


@api_endpoint(methods=("POST",))
def review_api(request, mistake_id):
    record = review_mistake(request.user, mistake_id)
    return {"id": record.pk, "last_reviewed_at": record.last_reviewed_at.isoformat()}


@api_endpoint()
def recommendations_api(request):
    return {"recommendations": get_recommendations(request.user, request.GET.get("mode", "foundation"), request.GET.get("target"))}
