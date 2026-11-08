"""Data-structures course domain manifest.

The manifest is data, not agent logic. The shared state machine only consumes
the capability/tool/policy fields.
"""

from django.conf import settings

from apps.platform.contracts import DomainPack, TaskPack


def build_domain_pack() -> DomainPack:
    return DomainPack(
        pack_id='data_structures',
        version='1.0.0',
        name='数据结构与算法课程',
        description='以课程原始 PDF 为权威证据的层次化检索与可核验问答。',
        capabilities=('text_retrieval', 'hierarchical_context', 'conflict_aware', 'multimodal_optional'),
        document_profile={
            'primary_format': 'pdf',
            'accepted_formats': ['pdf', 'docx', 'markdown', 'text', 'image', 'video', 'audio'],
            'required_metadata': ['document_hash', 'page_number', 'chapter', 'section'],
            'language': 'zh',
        },
        chunk_policy={
            'parent_token_min': getattr(settings, 'EVIDENCE_RAG_PARENT_TOKEN_MIN', 1200),
            'parent_token_max': getattr(settings, 'EVIDENCE_RAG_PARENT_TOKEN_MAX', 2000),
            'child_token_min': getattr(settings, 'EVIDENCE_RAG_CHILD_TOKEN_MIN', 300),
            'child_token_max': getattr(settings, 'EVIDENCE_RAG_CHILD_TOKEN_MAX', 500),
            'child_overlap_ratio': getattr(settings, 'EVIDENCE_RAG_CHILD_OVERLAP_RATIO', 0.12),
            'protected_blocks': ['fenced_code', 'table', 'display_math'],
        },
        metadata_schema={
            'document': ['source_type', 'authority_level', 'valid_from', 'valid_to', 'parser_name', 'ingestion_status'],
            'chunk': ['chunk_type', 'parent_chunk_id', 'heading_path', 'char_start', 'char_end', 'content_hash'],
        },
        authority_policy={
            'default_level': 3,
            'official_course_level': 1,
            'higher_is_better': False,
            'notes': '1 为最高权威；教师原始资料优先于外部补充。',
        },
        freshness_policy={
            'default_freshness': 0.7,
            'expired_freshness': 0.1,
            'future_freshness': 0.3,
            'max_age_days': 3650,
        },
        prompt_policy={
            'citation_required': True,
            'abstain_when_unsupported': True,
            'show_conflicts': True,
            'rewrite_is_not_evidence': True,
        },
        tool_manifest=(
            'keyword_search', 'semantic_search', 'read_child', 'read_parent',
            'read_siblings', 'read_source_page', 'retrieve_conflicting_versions',
        ),
        evaluation_cases=(
            'queue-complexity', 'queue-full', 'random-access', 'list-insert', 'linked-list',
            'stack-lifo', 'kmp-next', 'matrix-storage', 'generalized-list',
            'outside-redblack', 'outside-physics', 'conflict-negation', 'conflict-numeric',
            'conflict-version', 'conflict-unit', 'conflict-temporal',
        ),
    )


def build_task_packs() -> tuple[TaskPack, ...]:
    return (
        TaskPack(
            task_id='answer_with_evidence',
            domain_pack_id='data_structures',
            version='1.0.0',
            name='有证据回答',
            description='检索课程证据、核验引用并给出可追溯回答；证据不足时拒答。',
            required_capabilities=('text_retrieval', 'hierarchical_context'),
            tool_ids=('keyword_search', 'semantic_search', 'read_child', 'read_parent'),
            evaluation_case_ids=('queue-full', 'kmp-next', 'outside-physics'),
        ),
        TaskPack(
            task_id='compare_conflicting_evidence',
            domain_pack_id='data_structures',
            version='1.0.0',
            name='冲突证据对比',
            description='并列展示冲突双方、来源、版本与时间，不静默选择。',
            required_capabilities=('conflict_aware',),
            tool_ids=('retrieve_conflicting_versions', 'read_source_page'),
            evaluation_case_ids=('conflict-negation', 'conflict-numeric'),
        ),
        TaskPack(
            task_id='refuse_unsupported',
            domain_pack_id='data_structures',
            version='1.0.0',
            name='无证据拒答',
            description='库外或证据不足时 abstain，不生成未支撑结论。',
            required_capabilities=('text_retrieval',),
            tool_ids=('keyword_search', 'semantic_search'),
            evaluation_case_ids=('outside-redblack', 'outside-physics'),
        ),
    )
