"""Research-literature domain pack and comparison task manifest."""

from django.conf import settings

from apps.platform.contracts import DomainPack, TaskPack


def build_domain_pack() -> DomainPack:
    return DomainPack(
        pack_id='research_literature',
        version='1.0.0',
        name='科研文献比较包',
        description='面向论文 PDF/摘要的比较阅读：方法、实验条件、结论与局限必须绑定原文证据。',
        capabilities=('text_retrieval', 'hierarchical_context', 'semantic_retrieval', 'conflict_aware'),
        document_profile={
            'primary_format': 'pdf',
            'accepted_formats': ['pdf', 'docx', 'markdown', 'text'],
            'required_metadata': ['document_hash', 'source_type', 'version'],
            'language': 'auto',
        },
        chunk_policy={
            'parent_token_min': getattr(settings, 'EVIDENCE_RAG_PARENT_TOKEN_MIN', 1200),
            'parent_token_max': getattr(settings, 'EVIDENCE_RAG_PARENT_TOKEN_MAX', 2000),
            'child_token_min': getattr(settings, 'EVIDENCE_RAG_CHILD_TOKEN_MIN', 300),
            'child_token_max': getattr(settings, 'EVIDENCE_RAG_CHILD_TOKEN_MAX', 500),
            'child_overlap_ratio': getattr(settings, 'EVIDENCE_RAG_CHILD_OVERLAP_RATIO', 0.12),
            'protected_blocks': ['table', 'display_math', 'references'],
        },
        metadata_schema={
            'document': ['source_type', 'authority_level', 'valid_from', 'valid_to', 'version'],
            'chunk': ['chunk_type', 'heading_path', 'page_number', 'char_start', 'char_end'],
        },
        authority_policy={
            'default_level': 3,
            'peer_reviewed_level': 2,
            'preprint_level': 3,
            'higher_is_better': False,
            'notes': '预印本不等于低质量，但比较时须标注来源状态；重复转载不算独立佐证。',
        },
        freshness_policy={'default_freshness': 0.6, 'expired_freshness': 0.2, 'future_freshness': 0.3, 'max_age_days': 3650},
        prompt_policy={
            'citation_required': True,
            'abstain_when_unsupported': True,
            'show_conflicts': True,
            'comparison_requires_shared_fields': True,
        },
        tool_manifest=('keyword_search', 'semantic_search', 'read_child', 'read_parent', 'read_siblings', 'read_source_page'),
        evaluation_cases=('paper-compare-method', 'paper-missing-fulltext', 'paper-outside'),
    )


def build_task_packs() -> tuple[TaskPack, ...]:
    # The canonical paper_comparison task pack lives in ``task_packs.py`` so the
    # workbench has one definition and the UI cannot render duplicate options.
    return ()
