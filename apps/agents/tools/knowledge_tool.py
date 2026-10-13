from dataclasses import asdict,is_dataclass
from core.exceptions import ValidationError


def retrieve_course_knowledge(query: str,k: int = 4):
    if not query.strip() or len(query)>2000:
        raise ValidationError('课程检索问题为空或过长。')
    from apps.knowledge.services.retrieval_service import retrieve_knowledge
    result=retrieve_knowledge(query,top_k=max(1,min(k,6)))
    if is_dataclass(result): return asdict(result)
    if isinstance(result,list): return [asdict(item) if is_dataclass(item) else item for item in result]
    return result
