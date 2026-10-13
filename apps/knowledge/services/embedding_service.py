from functools import lru_cache
from pathlib import Path
from typing import Protocol
import hashlib
from django.conf import settings
from langchain_core.embeddings import Embeddings
from core.exceptions import KnowledgeRetrievalError

class EmbeddingProvider(Protocol):
    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...
    def embed_query(self, text: str) -> list[float]: ...

class BGEEmbeddings(Embeddings):
    def __init__(self):
        from sentence_transformers import SentenceTransformer
        try:
            self.model = SentenceTransformer(
                settings.EMBEDDING_MODEL, revision=settings.EMBEDDING_REVISION,
                local_files_only=getattr(settings, 'LOCAL_EMBEDDING_OFFLINE_MODE', True),
            )
        except Exception:
            raise KnowledgeRetrievalError('本地中文 Embedding 模型加载失败。请先联网运行 prepare_embedding_model；查询不会自动下载或切换向量模型。',code='EMBEDDING_UNAVAILABLE') from None
    def embed_documents(self,texts):
        return self.model.encode(texts,normalize_embeddings=True,show_progress_bar=False).tolist()
    def embed_query(self,text):
        return self.model.encode('为这个句子生成表示以用于检索相关文章：'+text,normalize_embeddings=True).tolist()

class TfidfEmbeddings(Embeddings):
    """Corpus-fitted Chinese character n-gram baseline, explicitly distinct from BGE."""
    def __init__(self, path: Path, texts: list[str] | None = None):
        import joblib
        from sklearn.feature_extraction.text import TfidfVectorizer
        if texts is not None:
            self.vectorizer = TfidfVectorizer(analyzer='char',ngram_range=(1,3),max_features=2048,sublinear_tf=True)
            self.vectorizer.fit(texts)
            path.parent.mkdir(parents=True,exist_ok=True)
            joblib.dump(self.vectorizer,path)
        elif path.is_file():
            self.vectorizer = joblib.load(path)
        else:
            raise KnowledgeRetrievalError('本地词向量未初始化，请执行 ingest_knowledge。')
    def embed_documents(self,texts): return self.vectorizer.transform(texts).toarray().tolist()
    def embed_query(self,text): return self.embed_documents([text])[0]


def embedding_identity() -> str:
    return f'{settings.EMBEDDING_PROVIDER}:{settings.EMBEDDING_MODEL}:{settings.EMBEDDING_REVISION}' if settings.EMBEDDING_PROVIDER == 'bge' else 'tfidf:char-1-3:2048:v1'


def embedding_path(index_version): return settings.BASE_DIR/'knowledge/processed'/f'embedding-{index_version}.joblib'


def build_embeddings(index_version: str, texts: list[str] | None = None) -> Embeddings:
    if settings.EMBEDDING_PROVIDER == 'bge': return bge_embeddings()
    if settings.EMBEDDING_PROVIDER == 'tfidf': return TfidfEmbeddings(embedding_path(index_version),texts)
    raise KnowledgeRetrievalError('不支持的 Embedding 提供方。')

@lru_cache(maxsize=1)
def bge_embeddings(): return BGEEmbeddings()

@lru_cache(maxsize=4)
def cached_embeddings(index_version): return build_embeddings(index_version)
