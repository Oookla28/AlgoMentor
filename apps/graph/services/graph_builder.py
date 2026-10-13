from django.db.models import Q
from apps.knowledge.models import KnowledgePoint, KnowledgeRelation, Chapter, KnowledgeChunk
from apps.problems.models import Submission
from apps.learning.models import MistakeRecord
from apps.learning.services.mastery_service import serialize_mastery, STATUS_LEVELS
from .graph_layout import ChapterLayout
from .graph_progress import get_progress, aggregate_progress
from .learning_path_service import dependency_graph, get_learning_path

CHAPTER_NAMES = {1: "绪论", 2: "线性表", 3: "栈与队列", 4: "串、数组和广义表"}


def get_graph(user, as_of=None):
    points = list(KnowledgePoint.objects.prefetch_related("prerequisites"))
    positions = ChapterLayout().layout(points)
    progress = get_progress(user, as_of)
    nodes, edges = [], []
    for point in points:
        x, y = positions[point.slug]
        nodes.append({"id": point.slug, "label": point.name, "kind": "knowledge", "chapter": point.chapter, "x": x, "y": y,
                      "source_page": point.source_page, "weight": point.difficulty,
                      **progress.get(point.pk, serialize_mastery(None))})
        edges.append({"source": f"chapter_{point.chapter:02d}", "target": point.slug, "type": "contains"})
    for chapter in range(1, 5):
        children = [node for node in nodes if node.get("chapter") == chapter and node["kind"] == "knowledge"]
        x, y = positions[f"chapter_{chapter:02d}"]
        nodes.append({"id": f"chapter_{chapter:02d}", "label": f"第{chapter}章 · {CHAPTER_NAMES[chapter]}", "kind": "chapter",
                      "chapter": chapter, "x": x, "y": y, **aggregate_progress(children)})
        edges.append({"source": "course", "target": f"chapter_{chapter:02d}", "type": "contains"})
    nodes.append({"id": "course", "label": "数据结构与算法", "kind": "course", "x": 700, "y": 50,
                  **aggregate_progress([node for node in nodes if node["kind"] == "knowledge"])})
    dag = dependency_graph()
    slug_by_id = {point.pk: point.slug for point in points}
    for source, target in dag.edges:
        edges.append({"source": slug_by_id[source], "target": slug_by_id[target], "type": "prerequisite"})
    for relation in KnowledgeRelation.objects.filter(relation_type="related").select_related("source", "target"):
        edges.append({"source": relation.source.slug, "target": relation.target.slug, "type": "related"})
    legend = [{"status": "UNSEEN", "label": "未学习", "color": "#aeb9c8"}] + [{"status": state, "label": label, "color": color, "threshold": lower} for lower, state, label, color in STATUS_LEVELS]
    return {"nodes": nodes, "edges": edges, "legend": legend, "width": 1400,
            "height": max((node["y"] for node in nodes), default=400) + 100, "version": "course-v1", "as_of": as_of.isoformat() if as_of else None}


def get_node_detail(user, slug):
    point = KnowledgePoint.objects.get(slug=slug)
    progress = get_progress(user).get(point.pk, serialize_mastery(None))
    submissions = Submission.objects.filter(user=user, problem__knowledge_points=point).exclude(status__in=["PENDING", "JUDGE_ERROR"])
    total, accepted = submissions.count(), submissions.filter(status="ACCEPTED").count()
    related = KnowledgeRelation.objects.filter(Q(source=point) | Q(target=point), relation_type="related").select_related("source", "target")
    chunks = KnowledgeChunk.objects.filter(page_number=point.source_page, source_type="original").select_related("document")[:3] if point.source_page else []
    return {"id": point.slug, "name": point.name, "chapter": point.chapter, "description": point.description, "source_page": point.source_page,
            "sources": [{"filename": chunk.document.name, "page": chunk.page_number, "chunk_id": chunk.chunk_id} for chunk in chunks],
            "prerequisites": [{"id": item.slug, "name": item.name} for item in point.prerequisites.all()],
            "related": [{"id": (relation.target if relation.source_id == point.pk else relation.source).slug, "name": (relation.target if relation.source_id == point.pk else relation.source).name} for relation in related],
            "completed_problems": submissions.filter(status="ACCEPTED").values("problem_id").distinct().count(),
            "recent_accuracy": round(accepted / total * 100, 2) if total else None,
            "mistakes": list(MistakeRecord.objects.filter(user=user, problem__knowledge_points=point).values("id", "error_type", "resolved", "problem__title")),
            "learning_path": get_learning_path(user, slug)["path"], **progress}
