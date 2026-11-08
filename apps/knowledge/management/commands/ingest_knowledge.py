import hashlib
from pathlib import Path
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from langchain_core.documents import Document
from langchain_chroma import Chroma
from apps.knowledge.models import KnowledgeDocument,KnowledgeChunk
from apps.knowledge.services.document_loader import load_document
from apps.knowledge.services.document_splitter import split_document
from apps.knowledge.services.embedding_service import build_embeddings,embedding_identity,cached_embeddings


def _legacy_ingest(path: Path, rebuild: bool, stdout):
    document = load_document(path)
    existing = KnowledgeDocument.objects.filter(document_hash=document.document_hash).first()
    if existing and existing.embedding_model == embedding_identity() and not rebuild:
        stdout.write(f'文件未变化：{existing.chunks.count()} 个片段，未重复入库。'); return
    chunks = split_document(document)
    index = hashlib.sha256((document.document_hash+embedding_identity()).encode()).hexdigest()[:24]
    embedding = build_embeddings(index,[c.content for c in chunks])
    dimension = len(embedding.embed_query('数据结构'))
    collection = f'course-{index}'
    store = Chroma(collection_name=collection,persist_directory=str(settings.CHROMA_PATH),embedding_function=embedding,collection_metadata={'hnsw:space':'cosine'})
    if rebuild:
        try:
            store.delete_collection()
        except Exception:
            pass
        store = Chroma(collection_name=collection,persist_directory=str(settings.CHROMA_PATH),embedding_function=embedding,collection_metadata={'hnsw:space':'cosine'})
    docs = [Document(page_content=c.content,metadata={'chunk_id':c.chunk_id,'document_name':document.name,'document_hash':document.document_hash,'chapter':c.chapter,'section':c.section,'page_number':c.page_number,'source_type':'original','version':'1'}) for c in chunks]
    store.add_documents(docs,ids=[c.chunk_id for c in chunks])
    if store._collection.count() != len(chunks): raise CommandError('向量索引数量不一致。')
    with transaction.atomic():
        row,created = KnowledgeDocument.objects.update_or_create(document_hash=document.document_hash,defaults={'name':document.name,'path':str(document.path.relative_to(settings.BASE_DIR)),'version':'1','page_count':len(document.pages),'embedding_model':embedding_identity(),'embedding_revision':settings.EMBEDDING_REVISION if settings.EMBEDDING_PROVIDER=='bge' else 'v1','embedding_dimension':dimension,'index_version':index,'collection_name':collection})
        for c in chunks:
            KnowledgeChunk.objects.update_or_create(chunk_id=c.chunk_id,defaults={'document':row,'chapter':c.chapter,'section':c.section,'page_number':c.page_number,'content':c.content,'source_type':'original','version':'1'})
        row.chunks.filter(chunk_type='legacy').exclude(chunk_id__in=[c.chunk_id for c in chunks]).delete()
    cached_embeddings.cache_clear()
    stdout.write(f'入库完成：{len(document.pages)} 页，{len(chunks)} 个片段，{dimension} 维；{embedding_identity()}；索引 {index}')
    return row


class Command(BaseCommand):
    help = '读取老师的原始课程 PDF 并幂等写入 Chroma；--advanced 追加层次化父/子索引'
    def add_arguments(self,parser):
        parser.add_argument('--path',default=str(settings.KNOWLEDGE_PATH/'数据结构与算法知识库文档.pdf'))
        parser.add_argument('--rebuild',action='store_true')
        parser.add_argument('--advanced',action='store_true',help='同时建立父块/子块与独立高级向量集合')
        parser.add_argument('--advanced-only',action='store_true',help='只建立高级索引，不改旧版索引')
    def handle(self,*args,**options):
        path = Path(options['path'])
        if options['advanced'] or options['advanced_only']:
            if not options['advanced_only'] and path.suffix.lower() == '.pdf':
                _legacy_ingest(path, options['rebuild'], self.stdout)
            from apps.knowledge.services.advanced_index_service import ingest_advanced
            outcome = ingest_advanced(path, rebuild=options['rebuild'] or True, index=True)
            document = outcome['document']
            parsed = outcome['parsed']
            index = outcome['index']
            if outcome['warning']:
                self.stdout.write(self.style.WARNING(f'高级索引未完成：{outcome["warning"]}'))
            if index:
                self.stdout.write(self.style.SUCCESS(
                    f'高级入库完成：父块 {parsed["parents"]}，子块 {parsed["children"]}，'
                    f'{index["embedding_dimension"]} 维；集合 {index["collection_name"]}；索引 {index["index_version"]}'
                ))
            else:
                self.stdout.write(f'高级切片已保存：父块 {parsed["parents"]}，子块 {parsed["children"]}；状态 {document.ingestion_status}')
            return
        _legacy_ingest(path, options['rebuild'], self.stdout)
