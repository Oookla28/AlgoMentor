import hashlib

from apps.knowledge.services.hierarchical_chunker import chunk_document, estimate_tokens, split_notes
from apps.knowledge.services.document_loader import LoadedDocument, SourcePage, load_document
from django.conf import settings


def _notes():
    return '''# 第一章 绪论

数据结构是计算机存储、组织数据的方式。算法是解决问题的步骤。复杂度用于衡量算法效率。

## 1.1 基本概念

数据元素是数据的基本单位。数据项是数据的最小单位。逻辑结构描述元素之间的关系。

## 1.2 算法分析

时间复杂度描述运行时间随输入规模的增长。空间复杂度描述额外空间需求。


# 第二章 线性表

线性表是由 n 个数据元素组成的有限序列。顺序表使用连续存储。链表使用指针连接。


## 2.1 顺序表

顺序表支持随机访问。插入和删除需要移动元素。平均移动次数约为 n/2。


## 2.2 链表

单链表每个结点包含数据域和指针域。双链表可以双向遍历。循环链表的尾结点指向头结点。

''' + ('这是补充说明，用于形成足够长的段落以便测试切片边界。' * 90)


def test_headings_create_parent_child_hierarchy():
    result = split_notes(_notes())
    assert result.has_headings is True
    assert result.structure_confidence >= 0.75
    assert len(result.parents) >= 2
    assert result.children
    parent_ids = {parent.chunk_id for parent in result.parents}
    assert all(child.parent_chunk_id in parent_ids for child in result.children)
    assert any('第一章' in parent.heading_path for parent in result.parents)
    assert any(child.heading_path for child in result.children)


def test_token_targets_and_overlap_are_reasonable():
    result = split_notes(_notes())
    child_tokens = [child.token_count for child in result.children]
    assert max(child_tokens) <= settings.EVIDENCE_RAG_CHILD_TOKEN_MAX + 80
    overlapping = [child for child in result.children if child.overlap_start]
    assert overlapping
    assert all(child.overlap_start <= int(settings.EVIDENCE_RAG_CHILD_TOKEN_MAX * 0.5) for child in overlapping)
    assert all(child.char_end > child.char_start for child in result.children)


def test_weak_structure_falls_back_without_failure():
    text = '这是一个没有任何标题的普通段落，用来验证弱结构回退。' * 300
    result = split_notes(text)
    assert result.has_headings is False
    assert result.structure_confidence < 0.45
    assert result.parents and result.children
    assert all(parent.parser_confidence < 0.45 for parent in result.parents)


def test_code_and_table_blocks_are_not_split():
    text = '# 第一章 示例\n\n' + ('普通文字。' * 220) + '''
```python
def add(a, b):
    return a + b
```

| 操作 | 复杂度 |
| --- | --- |
| 插入 | O(n) |
| 查找 | O(1) |
''' + ('结尾文字。' * 220)
    result = split_notes(text)
    fenced = [child for child in result.children if '```' in child.content]
    assert fenced
    assert all(child.content.count('```') == 2 for child in fenced)
    table = [child for child in result.children if '| 操作 |' in child.content]
    assert table
    assert all('| 查找 |' in child.content for child in table)


def test_content_hash_and_char_ranges_match_content():
    result = split_notes(_notes())
    for chunk in result.all_chunks:
        assert chunk.content_hash == hashlib.sha256(chunk.content.encode('utf-8')).hexdigest()
        assert chunk.char_end - chunk.char_start == len(chunk.content)
        assert chunk.token_count == estimate_tokens(chunk.content)


def test_page_numbers_follow_source_pages():
    document = LoadedDocument(
        path=__import__('pathlib').Path('demo.txt'),
        name='demo.txt',
        document_hash=hashlib.sha256(b'demo').hexdigest(),
        pages=(SourcePage(1, '# 第一章\n\n' + '第一页内容。' * 300), SourcePage(2, '第二页内容。' * 300)),
    )
    result = chunk_document(document)
    assert {chunk.page_number for chunk in result.parents} == {1, 2}
    assert {chunk.page_number for chunk in result.children} <= {1, 2}


def test_legacy_pdf_splitter_remains_available():
    from apps.knowledge.services.document_splitter import split_document
    document = load_document(settings.KNOWLEDGE_PATH / '数据结构与算法知识库文档.pdf')
    chunks = split_document(document)
    assert len(document.pages) == 15
    assert chunks and all(chunk.page_number for chunk in chunks)
