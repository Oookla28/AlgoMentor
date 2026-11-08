"""Second domain pack proving the core agent has no data-structures hardcoding."""

from django.conf import settings

from apps.platform.contracts import DomainPack, TaskPack


def build_domain_pack() -> DomainPack:
    return DomainPack(
        pack_id='general_documents',
        version='1.0.0',
        name='通用文档证据包',
        description='面向一般 PDF/文本/图片的通用证据检索；无课程专属权威假设。',
        capabilities=('text_retrieval', 'hierarchical_context', 'multimodal_optional'),
        document_profile={
            'primary_format': 'markdown',
            'accepted_formats': ['pdf', 'docx', 'markdown', 'text', 'image'],
            'required_metadata': ['document_hash', 'source_type'],
            'language': 'auto',
        },
        chunk_policy={
            'parent_token_min': getattr(settings, 'EVIDENCE_RAG_PARENT_TOKEN_MIN', 1200),
            'parent_token_max': getattr(settings, 'EVIDENCE_RAG_PARENT_TOKEN_MAX', 2000),
            'child_token_min': getattr(settings, 'EVIDENCE_RAG_CHILD_TOKEN_MIN', 300),
            'child_token_max': getattr(settings, 'EVIDENCE_RAG_CHILD_TOKEN_MAX', 500),
            'child_overlap_ratio': getattr(settings, 'EVIDENCE_RAG_CHILD_OVERLAP_RATIO', 0.12),
            'protected_blocks': ['fenced_code', 'table'],
        },
        metadata_schema={
            'document': ['source_type', 'authority_level', 'valid_from', 'valid_to', 'parser_name'],
            'chunk': ['chunk_type', 'heading_path', 'char_start', 'char_end', 'content_hash'],
        },
        authority_policy={
            'default_level': 3,
            'official_course_level': 3,
            'higher_is_better': False,
        },
        freshness_policy={
            'default_freshness': 0.7,
            'expired_freshness': 0.1,
            'future_freshness': 0.3,
            'max_age_days': 1825,
        },
        prompt_policy={
            'citation_required': True,
            'abstain_when_unsupported': True,
            'show_conflicts': True,
            'rewrite_is_not_evidence': True,
        },
        tool_manifest=(
            'keyword_search', 'semantic_search', 'read_child', 'read_parent',
            'read_siblings', 'read_source_page',
        ),
        evaluation_cases=('general-locate-definition', 'general-outside-topic'),
    )


def build_task_packs() -> tuple[TaskPack, ...]:
    return (
        TaskPack(
            task_id='locate_evidence',
            domain_pack_id='general_documents',
            version='1.0.0',
            name='定位证据',
            description='在通用文档中定位定义、数据或原文片段。',
            required_capabilities=('text_retrieval',),
            tool_ids=('keyword_search', 'semantic_search', 'read_child', 'read_parent'),
            evaluation_case_ids=('general-locate-definition',),
        ),
        TaskPack(
            task_id='summarize_document',
            domain_pack_id='general_documents',
            version='1.0.0',
            name='文档摘要',
            description='基于父块和相邻片段生成可引用的摘要。',
            required_capabilities=('hierarchical_context',),
            tool_ids=('read_parent', 'read_siblings', 'read_source_page'),
            evaluation_case_ids=('general-locate-definition',),
        ),
    )
