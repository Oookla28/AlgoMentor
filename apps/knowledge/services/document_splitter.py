import re
from dataclasses import dataclass
from langchain_text_splitters import RecursiveCharacterTextSplitter
from .document_loader import LoadedDocument

@dataclass(frozen=True)
class SourceChunk:
    chunk_id: str
    chapter: str
    section: str
    page_number: int
    content: str


def split_document(document: LoadedDocument) -> list[SourceChunk]:
    splitter = RecursiveCharacterTextSplitter(chunk_size=650,chunk_overlap=80,separators=['\n\n','\n','。','；','，',' ',''])
    chunks = []
    chapter = '课程知识库'
    section = '概念与示例'
    for page in document.pages:
        match = re.search(r'第[一二三四]章[^\n]*',page.text)
        if match: chapter = match.group(0).strip()
        for i, content in enumerate(splitter.split_text(page.text)):
            title = re.search(r'[•]\s*([^\n：:]{2,35})[：:]',content)
            if title: section = title.group(1).strip()
            chunks.append(SourceChunk(f'{document.document_hash[:24]}-p{page.page_number}-{i}',chapter,section,page.page_number,content))
    return chunks
