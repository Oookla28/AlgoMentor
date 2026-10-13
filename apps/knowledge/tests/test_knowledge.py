from pathlib import Path
import pytest
from django.conf import settings
from apps.knowledge.services.document_loader import load_document
from apps.knowledge.services.document_splitter import split_document
from apps.knowledge.services.retrieval_service import verified_citation_ids,Citation
from core.exceptions import KnowledgeRetrievalError

def test_original_pages_metadata_and_stable_chunks():
    doc=load_document(settings.KNOWLEDGE_PATH/'数据结构与算法知识库文档.pdf')
    chunks=split_document(doc)
    assert len(doc.pages)==15
    assert {c.page_number for c in chunks}==set(range(1,16))
    assert chunks==split_document(doc)
    assert any('循环队列' in c.content for c in chunks)

def test_citation_validation_rejects_invented_page_reference():
    with pytest.raises(KnowledgeRetrievalError): verified_citation_ids('见[来源9]',[])

@pytest.mark.django_db
def test_ingestion_idempotency_and_real_chroma_retrieval(settings,tmp_path):
    from django.core.management import call_command
    from apps.knowledge.models import KnowledgeDocument,KnowledgeChunk
    from apps.knowledge.services.embedding_service import cached_embeddings
    from apps.knowledge.services.retrieval_service import retrieve_knowledge
    settings.EMBEDDING_PROVIDER='tfidf'
    settings.RAG_MIN_SCORE=0.2
    settings.CHROMA_PATH=tmp_path/'chroma'
    settings.BASE_DIR=tmp_path
    # Preserve original input path while storing relative path under temporary base.
    import shutil
    source=tmp_path/'knowledge/original/数据结构与算法知识库文档.pdf';source.parent.mkdir(parents=True)
    shutil.copy2(Path(__file__).resolve().parents[3]/'knowledge/original/数据结构与算法知识库文档.pdf',source)
    call_command('ingest_knowledge',path=str(source))
    count=KnowledgeChunk.objects.count()
    call_command('ingest_knowledge',path=str(source))
    assert KnowledgeDocument.objects.count()==1
    assert KnowledgeChunk.objects.count()==count
    hits=retrieve_knowledge('循环队列判满条件')
    assert hits and any('队满' in h.content for h in hits)
    assert all(h.content==KnowledgeChunk.objects.get(chunk_id=h.chunk_id).content for h in hits)
    assert retrieve_knowledge('量子引力黑洞霍金辐射')==[]
    cached_embeddings.cache_clear()
