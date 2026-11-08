"""Cross-domain task templates.

A task pack describes *how* a task is carried out. It never grants tool access;
the executor intersects its declared tools with DomainPack, ToolSpec and the
caller's workspace permission before running anything.
"""

from apps.platform.contracts import TaskPack


def build_task_packs() -> tuple[TaskPack, ...]:
    return (
        TaskPack(
            task_id='grounded_qa',
            domain_pack_id='*',
            version='1.0.0',
            name='有据问答',
            description='检索空间内证据，逐句核验引用；证据不足时部分回答或拒答。',
            required_capabilities=('text_retrieval',),
            tool_ids=('keyword_search', 'semantic_search', 'read_child', 'read_parent', 'read_siblings'),
            evaluation_case_ids=('generic-locate', 'queue-full'),
        ),
        TaskPack(
            task_id='guided_learning',
            domain_pack_id='*',
            version='1.0.0',
            name='引导式学习',
            description='从资料生成可核验提纲、分层提示和一次自测；不更新掌握度成绩。',
            required_capabilities=('text_retrieval',),
            tool_ids=('keyword_search', 'semantic_search', 'read_child', 'read_parent'),
            evaluation_case_ids=('generic-locate',),
        ),
        TaskPack(
            task_id='paper_comparison',
            domain_pack_id='research_literature',
            version='1.0.0',
            name='文献比较',
            description='按方法、实验条件、结论与局限比较至少两篇文献，输出 Markdown/HTML 对照产物。',
            required_capabilities=('text_retrieval', 'semantic_retrieval'),
            tool_ids=('keyword_search', 'semantic_search', 'read_child', 'read_parent', 'read_siblings'),
            evaluation_case_ids=('paper-compare-method', 'paper-missing-fulltext'),
        ),
        TaskPack(
            task_id='code_investigation',
            domain_pack_id='software_engineering',
            version='1.0.0',
            name='代码问题分析',
            description='只读定位代码证据，给出风险与建议 diff，明确执行未验证。',
            required_capabilities=('text_retrieval', 'code_evidence'),
            tool_ids=('keyword_search', 'semantic_search', 'read_child', 'read_parent', 'read_siblings'),
            evaluation_case_ids=('code-locate-bug', 'code-without-runtime'),
        ),
    )
