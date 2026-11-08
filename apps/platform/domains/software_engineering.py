"""Software-engineering domain pack: read-only repository evidence and patch advice."""

from django.conf import settings

from apps.platform.contracts import DomainPack, TaskPack


def build_domain_pack() -> DomainPack:
    return DomainPack(
        pack_id='software_engineering',
        version='1.0.0',
        name='代码证据分析包',
        description='只读代码/文档证据定位，输出风险、建议 diff 与未验证的执行状态；不在主机执行用户代码。',
        capabilities=('text_retrieval', 'hierarchical_context', 'semantic_retrieval', 'code_evidence', 'conflict_aware'),
        document_profile={
            'primary_format': 'text',
            'accepted_formats': ['markdown', 'text', 'pdf', 'docx'],
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
            'document': ['source_type', 'authority_level', 'version', 'parser_name'],
            'chunk': ['chunk_type', 'heading_path', 'char_start', 'char_end'],
        },
        authority_policy={
            'default_level': 3,
            'source_code_level': 1,
            'design_doc_level': 2,
            'higher_is_better': False,
            'notes': '代码事实优先于注释与二手说明；注释不自动视为契约。',
        },
        freshness_policy={'default_freshness': 0.8, 'expired_freshness': 0.1, 'future_freshness': 0.3, 'max_age_days': 730},
        prompt_policy={
            'citation_required': True,
            'abstain_when_unsupported': True,
            'patch_requires_human_approval': True,
            'execution_status_must_be_explicit': True,
        },
        tool_manifest=('keyword_search', 'semantic_search', 'read_child', 'read_parent', 'read_siblings', 'read_source_page'),
        evaluation_cases=('code-locate-bug', 'code-suggest-patch', 'code-without-runtime'),
    )


def build_task_packs() -> tuple[TaskPack, ...]:
    # The canonical code_investigation task pack lives in ``task_packs.py``.
    return ()
