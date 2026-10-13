import networkx as nx
from apps.knowledge.models import KnowledgePoint, KnowledgeRelation
from apps.learning.models import MasteryState
from core.exceptions import ValidationError


def dependency_graph() -> nx.DiGraph:
    graph = nx.DiGraph()
    points = KnowledgePoint.objects.prefetch_related("prerequisites")
    for point in points:
        graph.add_node(point.pk, slug=point.slug)
        for before in point.prerequisites.all():
            graph.add_edge(before.pk, point.pk)
    for source, target in KnowledgeRelation.objects.filter(relation_type="prerequisite").values_list("source_id", "target_id"):
        graph.add_edge(source, target)
    if not nx.is_directed_acyclic_graph(graph):
        raise ValidationError("课程先修关系存在有向环，需管理员复核。", code="KNOWLEDGE_DEPENDENCY_CYCLE")
    return graph


def get_learning_path(user, target):
    point = KnowledgePoint.objects.get(slug=target)
    graph = dependency_graph()
    required = nx.ancestors(graph, point.pk) | {point.pk}
    subgraph = graph.subgraph(required)
    points = {item.pk: item for item in KnowledgePoint.objects.filter(pk__in=required)}
    states = {state.knowledge_point_id: state for state in MasteryState.objects.filter(user=user, knowledge_point_id__in=required)}
    result = []
    for point_id in nx.lexicographical_topological_sort(subgraph, key=lambda item: (points[item].chapter, points[item].order, points[item].slug)):
        current = points[point_id]
        index = states[point_id].index if point_id in states else 0
        if index >= 70 and point_id != point.pk:
            continue
        result.append({"id": current.slug, "name": current.name, "index": index, "is_target": point_id == point.pk,
                       "reason": "当前学习目标" if point_id == point.pk else f"{point.name} 的先修知识，当前尚未熟练",
                       "prerequisites": [points[parent].slug for parent in subgraph.predecessors(point_id)]})
    return {"target": point.slug, "path": result, "advisory": "此顺序为建议，可自主跳转。"}
