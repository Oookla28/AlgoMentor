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

class Command(BaseCommand):
    help = '读取老师的原始课程 PDF 并幂等写入 Chroma；更换向量配置需 --rebuild'
    def add_arguments(self,parser):
        parser.add_argument('--path',default=str(settings.KNOWLEDGE_PATH/'数据结构与算法知识库文档.pdf'))
        parser.add_argument('--rebuild',action='store_true')
    def handle(self,*args,**options):
        document = load_document(Path(options['path']))
        existing = KnowledgeDocument.objects.filter(document_hash=document.document_hash).first()
        if existing and existing.embedding_model == embedding_identity() and not options['rebuild']:
            self.stdout.write(f'文件未变化：{existing.chunks.count()} 个片段，未重复入库。'); return
        chunks = split_document(document)
        index = hashlib.sha256((document.document_hash+embedding_identity()).encode()).hexdigest()[:24]
        embedding = build_embeddings(index,[c.content for c in chunks])
        dimension = len(embedding.embed_query('数据结构'))
        collection = f'course-{index}'
        store = Chroma(collection_name=collection,persist_directory=str(settings.CHROMA_PATH),embedding_function=embedding,collection_metadata={'hnsw:space':'cosine'})
        docs = [Document(page_content=c.content,metadata={'chunk_id':c.chunk_id,'document_name':document.name,'document_hash':document.document_hash,'chapter':c.chapter,'section':c.section,'page_number':c.page_number,'source_type':'original','version':'1'}) for c in chunks]
        store.add_documents(docs,ids=[c.chunk_id for c in chunks])
        if store._collection.count() != len(chunks): raise CommandError('向量索引数量不一致。')
        with transaction.atomic():
            row,created = KnowledgeDocument.objects.update_or_create(document_hash=document.document_hash,defaults={'name':document.name,'path':str(document.path.relative_to(settings.BASE_DIR)),'version':'1','page_count':len(document.pages),'embedding_model':embedding_identity(),'embedding_revision':settings.EMBEDDING_REVISION if settings.EMBEDDING_PROVIDER=='bge' else 'v1','embedding_dimension':dimension,'index_version':index,'collection_name':collection})
            for c in chunks:
                KnowledgeChunk.objects.update_or_create(chunk_id=c.chunk_id,defaults={'document':row,'chapter':c.chapter,'section':c.section,'page_number':c.page_number,'content':c.content,'source_type':'original','version':'1'})
            row.chunks.exclude(chunk_id__in=[c.chunk_id for c in chunks]).delete()
        cached_embeddings.cache_clear()
        self.stdout.write(self.style.SUCCESS(f'入库完成：{len(document.pages)} 页，{len(chunks)} 个片段，{dimension} 维；{embedding_identity()}；索引 {index}'))
