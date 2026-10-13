import pytest
from django.contrib.auth import get_user_model
from apps.knowledge.models import KnowledgePoint, KnowledgeRelation
from apps.graph.services.learning_path_service import get_learning_path, dependency_graph
from apps.graph.services.graph_builder import get_graph
from core.exceptions import ValidationError


@pytest.mark.django_db
def test_learning_path_respects_prerequisites_not_related():
    user = get_user_model().objects.create_user(username="path")
    bf = KnowledgePoint.objects.create(slug="bf", name="BF", chapter=4, order=1)
    nxt = KnowledgePoint.objects.create(slug="next-array", name="next", chapter=4, order=2)
    kmp = KnowledgePoint.objects.create(slug="kmp", name="KMP", chapter=4, order=3)
    array = KnowledgePoint.objects.create(slug="array", name="数组", chapter=4, order=4)
    nxt.prerequisites.add(bf)
    kmp.prerequisites.add(nxt)
    KnowledgeRelation.objects.create(source=array, target=kmp, relation_type="related")
    path = get_learning_path(user, "kmp")["path"]
    assert [point["id"] for point in path] == ["bf", "next-array", "kmp"]
    first, second = get_graph(user), get_graph(user)
    assert first == second
    assert all(node["status"] == "UNSEEN" for node in first["nodes"])


@pytest.mark.django_db
def test_cycle_is_rejected_for_manual_review():
    first = KnowledgePoint.objects.create(slug="first", name="一", chapter=1)
    second = KnowledgePoint.objects.create(slug="second", name="二", chapter=1)
    first.prerequisites.add(second)
    second.prerequisites.add(first)
    with pytest.raises(ValidationError, match="有向环"):
        dependency_graph()
