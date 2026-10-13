from django.utils import timezone
from datetime import timedelta
from apps.knowledge.models import KnowledgePoint
from apps.problems.models import Submission, Problem
from apps.learning.models import MasteryState, MistakeRecord
from core.exceptions import ValidationError


def get_recommendations(user, mode="foundation", target=None, limit=5):
    modes = {"foundation": 1, "consolidation": 2, "challenge": 3}
    if mode not in modes:
        raise ValidationError("训练模式必须为基础、巩固或挑战。")
    states = {state.knowledge_point_id: state for state in MasteryState.objects.filter(user=user)}
    recent = set(Submission.objects.filter(user=user, created_at__gte=timezone.now() - timedelta(hours=24)).values_list("problem_id", flat=True))
    solved = set(Submission.objects.filter(user=user, status="ACCEPTED").values_list("problem_id", flat=True))
    mistakes = set(MistakeRecord.objects.filter(user=user, resolved=False).values_list("problem_id", flat=True))
    target_point = KnowledgePoint.objects.get(slug=target) if target else None
    candidate_points = set()
    if target_point:
        from apps.graph.services.learning_path_service import dependency_graph
        import networkx as nx
        dag = dependency_graph()
        candidate_points = {target_point.pk, *nx.ancestors(dag, target_point.pk)}
    candidates = []
    for problem in Problem.objects.filter(is_active=True).prefetch_related("knowledge_points"):
        points = list(problem.knowledge_points.all())
        if candidate_points and not any(point.pk in candidate_points for point in points):
            continue
        low = min((states[point.pk].index if point.pk in states else 0 for point in points), default=0)
        reason = "尚未练习此知识点，建立第一份学习证据。" if not any(point.pk in states for point in points) else f"关联知识点最低规则掌握指数为 {low:.0f}，适合继续训练。"
        score = 100 - low - abs(problem.difficulty - modes[mode]) * 25
        if problem.pk in mistakes:
            score += 30
            reason = "此题存在尚未解决的错误记录，建议根据分层提示再练习。"
        if target_point and target_point.pk not in {point.pk for point in points}:
            score += 15
            reason = f"这是 {target_point.name} 的未熟练先修知识，先巩固有助于后续学习。"
        if problem.pk in solved:
            score -= 45
        if problem.pk in recent:
            score -= 60
        candidates.append((problem.pk in recent, -score, problem.pk, {"problem_id": problem.pk, "slug": problem.slug,
            "title": problem.title, "difficulty": problem.difficulty, "knowledge_points": [{"id": point.slug, "name": point.name} for point in points],
            "reason": reason, "objective": "独立完成并验证边界输入", "recently_attempted": problem.pk in recent}))
    candidates.sort(key=lambda value: value[:3])
    return [value[3] for value in candidates[:max(1, min(limit, 20))]]
