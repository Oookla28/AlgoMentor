"""Lightweight BM25 lexical retrieval over Chinese course text.

No Elasticsearch/Redis is required: the corpus is tokenised in-process and
scored with a small BM25 implementation. CJK characters contribute unigrams
and bigrams, which provides useful recall without a segmentation dependency.
"""

from dataclasses import dataclass
import math
import re
import unicodedata

from django.conf import settings

_STOPWORDS = {
    '的', '了', '是', '在', '和', '与', '及', '或', '有', '为', '对', '中', '上', '下',
    '我', '你', '他', '她', '它', '这', '那', '哪些', '什么', '怎么', '如何', '为什么',
    '请问', '请', '解释', '说明', '介绍', '一下', '一个', '可以', '需要', '以及', '关于',
    'the', 'a', 'an', 'is', 'are', 'of', 'to', 'and', 'or', 'in', 'on', 'for', 'what', 'how', 'why',
}
_CJK_RE = re.compile(r'[\u3400-\u4dbf\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]')
_ASCII_RE = re.compile(r'[a-z0-9_+.]+')


@dataclass(frozen=True)
class SparseHit:
    chunk_id: str
    score: float
    rank: int
    raw_score: float = 0.0


def tokenize(text: str) -> list[str]:
    text = unicodedata.normalize('NFKC', str(text or '')).lower()
    tokens = []
    for word in _ASCII_RE.findall(text):
        if word not in _STOPWORDS and len(word) > 1:
            tokens.append(word)
    cjk = [char for char in text if _CJK_RE.match(char)]
    tokens.extend(char for char in cjk if char not in _STOPWORDS)
    tokens.extend(a + b for a, b in zip(cjk, cjk[1:]) if (a + b) not in _STOPWORDS)
    return tokens


class BM25Index:
    def __init__(self, documents, k1=1.5, b=0.75):
        self.documents = [(str(chunk_id), str(text or '')) for chunk_id, text in documents]
        self.k1 = k1
        self.b = b
        self.doc_tokens = [tokenize(text) for _chunk_id, text in self.documents]
        self.doc_lengths = [len(tokens) for tokens in self.doc_tokens]
        self.average_length = sum(self.doc_lengths) / len(self.doc_lengths) if self.doc_lengths else 0.0
        self.term_frequencies = []
        self.document_frequency = {}
        for tokens in self.doc_tokens:
            frequencies = {}
            for token in tokens:
                frequencies[token] = frequencies.get(token, 0) + 1
            self.term_frequencies.append(frequencies)
            for token in frequencies:
                self.document_frequency[token] = self.document_frequency.get(token, 0) + 1

    def _idf(self, token: str) -> float:
        total = len(self.documents)
        frequency = self.document_frequency.get(token, 0)
        return math.log(1 + (total - frequency + 0.5) / (frequency + 0.5))

    def search(self, query: str, top_k: int = 20) -> list[SparseHit]:
        query_tokens = tokenize(query)
        if not query_tokens or not self.documents:
            return []
        query_counts = {}
        for token in query_tokens:
            query_counts[token] = query_counts.get(token, 0) + 1
        scored = []
        for index, (chunk_id, _text) in enumerate(self.documents):
            length = self.doc_lengths[index]
            frequencies = self.term_frequencies[index]
            score = 0.0
            for token, query_frequency in query_counts.items():
                frequency = frequencies.get(token, 0)
                if not frequency:
                    continue
                denominator = frequency + self.k1 * (1 - self.b + self.b * length / (self.average_length or 1))
                score += self._idf(token) * (frequency * (self.k1 + 1) / denominator) * (1 + math.log(query_frequency))
            if score > 0:
                scored.append((chunk_id, score))
        scored.sort(key=lambda item: (-item[1], item[0]))
        scored = scored[:max(1, top_k)]
        largest = scored[0][1] if scored else 0.0
        return [
            SparseHit(chunk_id=chunk_id, score=round(score / largest, 6) if largest else 0.0, rank=rank, raw_score=round(score, 6))
            for rank, (chunk_id, score) in enumerate(scored, 1)
        ]


def load_advanced_documents(document_ids=None):
    from apps.knowledge.models import KnowledgeChunk
    queryset = KnowledgeChunk.objects.filter(is_active=True).exclude(chunk_type='parent')
    if document_ids:
        queryset = queryset.filter(document_id__in=document_ids)
    advanced = list(queryset.filter(chunk_type__in=['child', 'media']).values_list('chunk_id', 'content'))
    if advanced:
        return advanced
    return list(queryset.filter(chunk_type='legacy').values_list('chunk_id', 'content'))


def sparse_search(query: str, documents=None, top_k: int | None = None) -> list[SparseHit]:
    documents = load_advanced_documents() if documents is None else list(documents)
    if not documents:
        return []
    top_k = top_k or getattr(settings, 'EVIDENCE_RAG_ROUTE_TOP_K', 20)
    return BM25Index(documents).search(query, top_k=top_k)
