from dataclasses import dataclass, asdict
from typing import Protocol
from django.conf import settings
from langchain_chroma import Chroma
from core.exceptions import KnowledgeRetrievalError, ValidationError
from apps.knowledge.models import KnowledgeDocument, KnowledgeChunk
from .embedding_service import cached_embeddings, embedding_identity
from apps.knowledge.models import KnowledgeCorrection

@dataclass(frozen=True)
class Citation:
    chunk_id: str
    document_name: str
    document_hash: str
    chapter: str
    section: str
    page_number: int
    content: str
    source_type: str
    version: str
    score: float
    url: str

class VectorStore(Protocol):
    def search(self, query: str, k: int) -> list[Citation]: ...


def retrieve_knowledge(query: str, top_k: int | None = None) -> list[Citation]:
    query = query.strip()
    if not query or len(query) > 2000: raise ValidationError('检索问题须为 1 至 2000 字。')
    documents = list(KnowledgeDocument.objects.order_by('-created_at'))
    if not documents: raise KnowledgeRetrievalError('知识库尚未入库，请先执行 ingest_knowledge。',code='INDEX_MISSING')
    k = max(1,min(top_k or settings.RAG_TOP_K,8))
    hits = []
    # Each document/index has its own dimensions and vocabulary; never mix vectors.
    for document in documents:
        if document.embedding_model != embedding_identity(): continue
        store = Chroma(collection_name=document.collection_name,persist_directory=str(settings.CHROMA_PATH),embedding_function=cached_embeddings(document.index_version),collection_metadata={'hnsw:space':'cosine'})
        for item,distance in store.similarity_search_with_score(query,k=k):
            chunk = KnowledgeChunk.objects.filter(chunk_id=item.metadata.get('chunk_id'),document=document).first()
            score = max(0.0,min(1.0,1-float(distance)))
            if not chunk or score < settings.RAG_MIN_SCORE: continue
            hits.append(Citation(chunk.chunk_id,document.name,document.document_hash,chunk.chapter,chunk.section,chunk.page_number,chunk.content,chunk.source_type,chunk.version,round(score,4),f'/knowledge/source/{chunk.chunk_id}/'))
    if not any(d.embedding_model == embedding_identity() for d in documents):
        raise KnowledgeRetrievalError('Embedding 配置与已入库索引不一致，请重新入库。',code='INDEX_VERSION_MISMATCH')
    selected = sorted(hits,key=lambda h:h.score,reverse=True)[:k]
    correction_hits = []
    for hit in selected:
        for correction in KnowledgeCorrection.objects.filter(chunk__chunk_id=hit.chunk_id,status='APPROVED',reviewed_by__isnull=False):
            correction_hits.append(Citation(f'correction-{correction.pk}',hit.document_name,hit.document_hash,hit.chapter,'经教师审核的勘误',hit.page_number,correction.suggested_statement+'\n核验：'+correction.verification,'correction',str(correction.pk),hit.score,hit.url))
    return selected + correction_hits


def citations_json(citations): return [asdict(c) for c in citations]


def verified_citation_ids(text: str, citations: list[Citation]) -> list[Citation]:
    import re
    ids = {int(x) for x in re.findall(r'\[来源(\d+)\]',text)}
    if any(i < 1 or i > len(citations) for i in ids):
        raise KnowledgeRetrievalError('回答含未经核验的来源编号，请重试。',code='CITATION_INVALID')
    return [c for i,c in enumerate(citations,1) if i in ids]
