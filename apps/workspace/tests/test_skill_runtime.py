import json
from pathlib import Path

import pytest

from apps.platform.domains import get_domain_pack, get_task_pack
from apps.platform.skills import (
    SkillError, catalog, load_registry, load_skill, resolve_tool_scope, select_skills, skills_health,
)


def test_native_skill_catalog_loads_with_real_hashes():
    entries = catalog()
    assert len(entries) >= 6
    by_id = {entry['skill_id']: entry for entry in entries}
    assert {
        'grounded-knowledge-answering', 'evidence-paper-comparison', 'repository-investigation',
        'guided-learning', 'experiment-review', 'task-recovery',
    } <= set(by_id)
    assert all(entry['state'] == 'available' for entry in entries)
    assert all(len(entry.get('content_hash', '')) == 64 for entry in entries)
    health = skills_health()
    assert health['state'] == 'available'
    assert health['failed'] == 0


def test_skill_selection_is_deterministic_and_bounded():
    paper = select_skills('paper_comparison', 'research_literature', '比较两篇论文的方法')
    assert [skill.skill_id for skill in paper] == ['evidence-paper-comparison']
    code = select_skills('code_investigation', 'software_engineering', '这段代码哪里有问题')
    assert [skill.skill_id for skill in code] == ['repository-investigation']
    retry = select_skills('grounded_qa', 'generic', '重试', attempts=1)
    assert retry[0].skill_id == 'task-recovery'
    assert len(retry) <= 2


def test_skill_tool_scope_can_only_narrow_permissions():
    task = get_task_pack('paper_comparison', 'research_literature')
    domain = get_domain_pack('research_literature')
    skill = next(item for item in load_registry() if item.skill_id == 'evidence-paper-comparison')
    scope = resolve_tool_scope(task, domain, skill, {
        'keyword_search', 'semantic_search', 'read_child', 'execute_shell',
    })
    assert 'execute_shell' not in scope
    assert set(scope) <= set(skill.allowed_tools)
    assert set(scope) <= set(task.tool_ids) & set(domain.tool_manifest)


def test_registry_rejects_path_traversal(tmp_path):
    root = tmp_path / 'agent_skills'
    (root / 'runtime').mkdir(parents=True)
    (root / 'registry.json').write_text(json.dumps({'skills': [{
        'id': 'evil', 'version': '1', 'entry': 'runtime/../secret.md',
        'allowed_tools': [], 'task_types': [],
    }]}), encoding='utf-8')
    with pytest.raises(SkillError) as captured:
        load_registry(root)
    assert captured.value.code in ('SKILL_PATH_INVALID', 'SKILL_PATH_TRAVERSAL')


def test_registry_rejects_symlinked_skill(tmp_path):
    root = tmp_path / 'agent_skills'
    (root / 'runtime').mkdir(parents=True)
    outside = tmp_path / 'outside.md'
    outside.write_text('---\nname: x\n---\nbody', encoding='utf-8')
    (root / 'runtime' / 'link.md').symlink_to(outside)
    (root / 'registry.json').write_text(json.dumps({'skills': [{
        'id': 'link', 'version': '1', 'entry': 'runtime/link.md',
        'allowed_tools': [], 'task_types': [],
    }]}), encoding='utf-8')
    with pytest.raises(SkillError) as captured:
        load_registry(root)
    assert captured.value.code == 'SKILL_SYMLINK_REJECTED'


def test_oversized_skill_and_invalid_yaml_are_rejected(tmp_path):
    root = tmp_path / 'agent_skills'
    runtime = root / 'runtime'
    runtime.mkdir(parents=True)
    oversized = runtime / 'big.md'
    oversized.write_text('---\nname: big\n---\n' + ('x' * (70 * 1024)), encoding='utf-8')
    (root / 'registry.json').write_text(json.dumps({'skills': [{
        'id': 'big', 'version': '1', 'entry': 'runtime/big.md',
        'allowed_tools': [], 'task_types': [],
    }]}), encoding='utf-8')
    with pytest.raises(SkillError) as captured:
        load_registry(root)
    assert captured.value.code == 'SKILL_TOO_LARGE'


def test_missing_registry_keeps_base_path_available(tmp_path):
    assert load_registry(tmp_path / 'missing') == []
    assert select_skills('grounded_qa', 'generic', root=tmp_path / 'missing') == []
