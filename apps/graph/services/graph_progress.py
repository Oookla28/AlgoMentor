from types import SimpleNamespace
from apps.learning.models import MasteryState, MasterySnapshot
from apps.learning.services.mastery_service import serialize_mastery, mastery_label


def get_progress(user, as_of=None):
    if as_of is None:
        return {state.knowledge_point_id: serialize_mastery(state) for state in MasteryState.objects.filter(user=user)}
    # Real snapshots only, including regressions; no interpolated fake history.
    latest = {}
    for snapshot in MasterySnapshot.objects.filter(user=user, created_at__lte=as_of).order_by("created_at", "pk"):
        latest[snapshot.knowledge_point_id] = serialize_mastery(SimpleNamespace(index=snapshot.index,
            bkt_probability=snapshot.bkt_probability, evidence_count=snapshot.evidence_count, distinct_problems=0,
            explanation={"message": "历史快照", "at": snapshot.created_at.isoformat()}))
    return latest


def aggregate_progress(children):
    weight = sum(child.get("weight", 1) for child in children)
    index = sum(child["index"] * child.get("weight", 1) for child in children) / weight if weight else 0
    learned = sum(child["evidence_count"] > 0 for child in children)
    evidence = sum(child["evidence_count"] for child in children)
    return {"index": round(index, 2), "evidence_count": evidence, "knowledge_count": len(children), "learned_points": learned,
            "mastered_points": sum(child["status"] == "MASTERED" for child in children),
            "coverage": round(100 * learned / len(children), 2) if children else 0, **mastery_label(index, evidence)}
