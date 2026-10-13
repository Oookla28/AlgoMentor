from dataclasses import dataclass
from pathlib import Path
import hashlib
from pypdf import PdfReader
from core.exceptions import KnowledgeRetrievalError

@dataclass(frozen=True)
class SourcePage:
    page_number: int
    text: str

@dataclass(frozen=True)
class LoadedDocument:
    path: Path
    name: str
    document_hash: str
    pages: tuple[SourcePage, ...]


def load_document(path: Path) -> LoadedDocument:
    if not path.is_file() or path.suffix.lower() != '.pdf':
        raise KnowledgeRetrievalError('原始 PDF 文件不存在。')
    reader = PdfReader(path)
    pages = tuple(SourcePage(i + 1, (page.extract_text() or '').replace('\u200b','').replace('\ufeff','')) for i, page in enumerate(reader.pages))
    if not any(p.text.strip() for p in pages):
        raise KnowledgeRetrievalError('PDF 无可提取文本，需要先进行 OCR。')
    return LoadedDocument(path, path.name, hashlib.sha256(path.read_bytes()).hexdigest(), pages)
