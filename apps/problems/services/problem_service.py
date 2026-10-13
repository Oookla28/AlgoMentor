from apps.problems.models import Problem
from django.db.models import Q


def problem_queryset(difficulty=None, point=None, chapter=None, query=None):
    result = Problem.objects.filter(is_active=True).prefetch_related("knowledge_points")
    if str(difficulty) in ("1", "2", "3"):
        result = result.filter(difficulty=difficulty)
    if point:
        result = result.filter(knowledge_points__slug=point)
    if str(chapter) in ("1", "2", "3", "4"):
        result = result.filter(knowledge_points__chapter=chapter)
    if query:
        result = result.filter(Q(title__icontains=str(query)[:100]) | Q(description__icontains=str(query)[:100]))
    return result.distinct()
