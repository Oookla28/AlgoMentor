from datetime import datetime, time
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.utils.dateparse import parse_datetime, parse_date
from core.http import api_endpoint, json_body
from core.exceptions import ValidationError
from .services.graph_builder import get_graph, get_node_detail
from .services.graph_progress import get_progress
from .services.learning_path_service import get_learning_path
from .services.algorithm_service import generate_steps


@login_required
def index(request):
    return render(request, "graph/index.html", {"graph_data": get_graph(request.user)})


@login_required
def visualization(request):
    return render(request, "visualization/index.html")


@api_endpoint()
def graph_api(request):
    as_of = None
    if request.GET.get("as_of"):
        value = request.GET["as_of"]
        try:
            as_of = parse_datetime(value)
            if as_of is None:
                date = parse_date(value)
                if date:
                    as_of = datetime.combine(date, time.max)
        except (TypeError, ValueError) as exc:
            raise ValidationError("历史日期格式无效。") from exc
        if as_of is None:
            raise ValidationError("历史日期格式应为 ISO 日期或时间。")
        if timezone.is_naive(as_of):
            as_of = timezone.make_aware(as_of)
    return get_graph(request.user, as_of)


@api_endpoint()
def node_api(request, slug):
    return get_node_detail(request.user, slug)


@api_endpoint()
def progress_api(request):
    return {"progress": get_progress(request.user)}


@api_endpoint()
def path_api(request):
    target = request.GET.get("target")
    if not target:
        raise ValidationError("请选择目标知识点。")
    return get_learning_path(request.user, target)


@api_endpoint(methods=("POST",))
def algorithm_api(request):
    return generate_steps(json_body(request))
