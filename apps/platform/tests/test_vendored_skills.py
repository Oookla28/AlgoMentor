import hashlib
import json
from pathlib import Path

import pytest

from apps.platform.skills.development import audit, load_body, load_index
from apps.platform.skills.runtime import select_skills, skills_health


def test_vendored_development_skills_are_pinned_and_verified():
    result = audit()
    assert result['state'] == 'available'
    assert result['count'] >= 8
    assert result['failed'] == 0
    ids = {row['skill_id'] for row in result['skills']}
    assert {
        'dev-frontend-design', 'dev-webapp-testing', 'dev-systematic-debugging',
        'dev-test-driven-development', 'dev-verification-before-completion',
        'dev-skill-creator', 'runtime-literature-review-reference',
        'runtime-scientific-critical-thinking-reference',
    } <= ids
    for row in result['skills']:
        assert row['state'] == 'verified'
        assert row['executable_in_product_runtime'] is False
        assert len(row['upstream_commit_sha']) == 40
        assert len(row['actual_skill_sha256']) == 64
        assert len(row['actual_license_sha256']) == 64
        assert Path(row['resolved_skill_path']).is_file()
        assert Path(row['resolved_license_path']).is_file()
    body = load_body('dev-frontend-design')
    assert 'frontend-design' in body['body']
    assert body['license'] == 'Apache-2.0'


def test_vendored_skills_are_not_runtime_skills():
    health = skills_health()
    assert health['state'] == 'available'
    runtime_ids = {row['skill_id'] for row in health['skills']}
    development_ids = {row['skill_id'] for row in load_index()}
    assert runtime_ids.isdisjoint(development_ids)
    selected = select_skills('paper_comparison', 'research_literature', '比较方法')
    assert [skill.skill_id for skill in selected] == ['evidence-paper-comparison']


def test_tampered_vendored_body_is_detected(tmp_path):
    base = tmp_path / 'agent_skills'
    vendor = base / 'vendor' / 'demo'
    vendor.mkdir(parents=True)
    body = vendor / 'SKILL.md'
    license_file = vendor / 'LICENSE.txt'
    body.write_text('---\nname: demo\n---\nbody', encoding='utf-8')
    license_file.write_text('MIT', encoding='utf-8')
    index = {
        'schema_version': 1,
        'skills': [{
            'skill_id': 'dev-demo', 'source_id': 'demo', 'repo': 'demo/demo',
            'upstream_commit_sha': 'a' * 40, 'target': 'development-agent-only',
            'state': 'VENDORED_REFERENCE', 'executable_in_product_runtime': False,
            'skill_path': 'agent_skills/vendor/demo/SKILL.md',
            'skill_sha256': '0' * 64, 'skill_bytes': body.stat().st_size,
            'license': 'MIT',
            'license_path': 'agent_skills/vendor/demo/LICENSE.txt',
            'license_sha256': hashlib.sha256(license_file.read_bytes()).hexdigest(),
        }],
    }
    (base / 'development').mkdir(parents=True)
    (base / 'development' / 'index.json').write_text(json.dumps(index), encoding='utf-8')
    result = audit(root=base)
    assert result['state'] == 'failed'
    assert result['skills'][0]['problems'] == ['SKILL_HASH_MISMATCH']


def test_symlinked_vendored_skill_is_rejected(tmp_path):
    base = tmp_path / 'agent_skills'
    vendor = base / 'vendor'
    vendor.mkdir(parents=True)
    outside = tmp_path / 'outside.md'
    outside.write_text('body', encoding='utf-8')
    (vendor / 'link.md').symlink_to(outside)
    index = {
        'schema_version': 1,
        'skills': [{
            'skill_id': 'dev-link', 'source_id': 'x', 'repo': 'x/x',
            'upstream_commit_sha': 'a' * 40, 'target': 'development-agent-only',
            'state': 'VENDORED_REFERENCE', 'executable_in_product_runtime': False,
            'skill_path': 'agent_skills/vendor/link.md', 'skill_sha256': '0' * 64,
            'skill_bytes': 4, 'license': 'MIT',
            'license_path': 'agent_skills/vendor/link.md', 'license_sha256': '0' * 64,
        }],
    }
    (base / 'development').mkdir(parents=True)
    (base / 'development' / 'index.json').write_text(json.dumps(index), encoding='utf-8')
    result = audit(root=base)
    assert result['state'] == 'failed'
    assert result['error_code'] == 'DEVELOPMENT_SKILL_SYMLINK_REJECTED'
