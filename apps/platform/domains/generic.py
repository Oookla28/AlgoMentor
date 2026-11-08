"""Generic document pack used by newly created personal workspaces."""

from django.conf import settings

from apps.platform.contracts import DomainPack, TaskPack


def build_domain_pack() -> DomainPack:
    return DomainPack(
        pack_id='generic',
        version='1.0.0',
        name='通用资料空间',
        description='面向个人笔记、课程补充材料和自由文档的通用证据检索。',
        capabilities=('text_retrieval', 'hierarchical_context', 'semantic_retrieval', 'multimodal_optional'),
        document_profile={
            'primary_format': 'markdown',
            'accepted_formats': ['pdf', 'docx', 'markdown', 'text', 'image', 'audio', 'video'],
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
        authority_policy={'default_level': 3, 'higher_is_better': False},
        freshness_policy={'default_freshness': 0.7, 'expired_freshness': 0.1, 'future_freshness': 0.3, 'max_age_days': 1825},
        prompt_policy={'citation_required': True, 'abstain_when_unsupported': True, 'show_conflicts': True},
        tool_manifest=('keyword_search', 'semantic_search', 'read_child', 'read_parent', 'read_siblings', 'read_source_page'),
        evaluation_cases=('generic-locate', 'generic-outside'),
    )


def build_task_packs() -> tuple[TaskPack, ...]:
    return (
        TaskPack(
            task_id='generic_locate_evidence',
            domain_pack_id='generic',
            version='1.0.0',
            name='通用资料定位',
            description='在个人资料中定位原文并给出可核验引用。',
            required_capabilities=('text_retrieval',),
            tool_ids=('keyword_search', 'semantic_search', 'read_child', 'read_parent'),
            evaluation_case_ids=('generic-locate',),
        ),
    )
