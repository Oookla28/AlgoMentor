"""Vendored development-agent skills: auditable, never runtime-executable.

These files are pinned copies of upstream SKILL.md and license files. They are
for maintainers/development agents only. The product runtime loads only
``agent_skills/runtime`` through ``apps.platform.skills.runtime``.
"""

import hashlib
import json
from pathlib import Path

from django.conf import settings

MAX_INDEX_BYTES = 512 * 1024
MAX_BODY_BYTES = 512 * 1024


class DevelopmentSkillError(Exception):
    def __init__(self, code, message=''):
        super().__init__(message or code)
        self.code = code
        self.message = message or code


def _root(root=None):
    return Path(root) if root is not None else Path(settings.BASE_DIR) / 'agent_skills'


def _safe_path(relative, base):
    relative_path = Path(str(relative))
    base = base.resolve()
    if relative_path.is_absolute() or '..' in relative_path.parts:
        raise DevelopmentSkillError('DEVELOPMENT_SKILL_PATH_TRAVERSAL', '开发 Skill 路径越界。')
    current = base
    for part in relative_path.parts:
        current = current / part
        if current.is_symlink():
            raise DevelopmentSkillError('DEVELOPMENT_SKILL_SYMLINK_REJECTED', '拒绝符号链接开发 Skill。')
    candidate = current.resolve()
    if base != candidate and base not in candidate.parents:
        raise DevelopmentSkillError('DEVELOPMENT_SKILL_PATH_TRAVERSAL', '开发 Skill 路径越界。')
    return candidate


def _sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_index(root=None):
    base = _root(root)
    base_dir = base.parent
    index_path = base / 'development' / 'index.json'
    if not index_path.is_file():
        raise DevelopmentSkillError('DEVELOPMENT_SKILL_INDEX_MISSING', '开发 Skill 索引不存在。')
    if index_path.stat().st_size > MAX_INDEX_BYTES:
        raise DevelopmentSkillError('DEVELOPMENT_SKILL_INDEX_TOO_LARGE', '开发 Skill 索引超过大小限制。')
    try:
        payload = json.loads(index_path.read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        raise DevelopmentSkillError('DEVELOPMENT_SKILL_INDEX_INVALID', '开发 Skill 索引无法解析。') from exc
    skills = payload.get('skills') if isinstance(payload, dict) else None
    if not isinstance(skills, list):
        raise DevelopmentSkillError('DEVELOPMENT_SKILL_INDEX_INVALID', '开发 Skill 索引结构无效。')
    rows = []
    seen = set()
    for raw in skills:
        if not isinstance(raw, dict) or not raw.get('skill_id'):
            raise DevelopmentSkillError('DEVELOPMENT_SKILL_INDEX_INVALID', '开发 Skill 条目无效。')
        skill_id = str(raw['skill_id'])
        if skill_id in seen:
            raise DevelopmentSkillError('DEVELOPMENT_SKILL_DUPLICATE', f'重复开发 Skill：{skill_id}')
        seen.add(skill_id)
        skill_path = _safe_path(raw['skill_path'], base_dir)
        license_path = _safe_path(raw['license_path'], base_dir)
        if not skill_path.is_file() or not license_path.is_file():
            raise DevelopmentSkillError('DEVELOPMENT_SKILL_FILE_MISSING', f'{skill_id} 文件缺失。')
        if skill_path.stat().st_size > MAX_BODY_BYTES:
            raise DevelopmentSkillError('DEVELOPMENT_SKILL_TOO_LARGE', f'{skill_id} 正文过大。')
        rows.append({
            **raw,
            'resolved_skill_path': str(skill_path),
            'resolved_license_path': str(license_path),
            'actual_skill_sha256': _sha256(skill_path),
            'actual_license_sha256': _sha256(license_path),
        })
    return rows


def audit(root=None):
    try:
        rows = load_index(root)
    except DevelopmentSkillError as exc:
        return {'state': 'failed', 'error_code': exc.code, 'skills': []}
    for row in rows:
        problems = []
        if row['actual_skill_sha256'] != row.get('skill_sha256'):
            problems.append('SKILL_HASH_MISMATCH')
        if row['actual_license_sha256'] != row.get('license_sha256'):
            problems.append('LICENSE_HASH_MISMATCH')
        if row.get('executable_in_product_runtime'):
            problems.append('RUNTIME_EXECUTION_FORBIDDEN')
        row['state'] = 'verified' if not problems else 'failed'
        row['problems'] = problems
    failed = [row for row in rows if row['state'] == 'failed']
    return {
        'state': 'failed' if failed else 'available',
        'count': len(rows),
        'failed': len(failed),
        'skills': rows,
    }


def load_body(skill_id, root=None):
    """Load a vendored body for a development agent after hash verification."""
    for row in load_index(root):
        if row['skill_id'] != skill_id:
            continue
        if row['actual_skill_sha256'] != row.get('skill_sha256'):
            raise DevelopmentSkillError('DEVELOPMENT_SKILL_HASH_MISMATCH', '开发 Skill 已被修改。')
        text = Path(row['resolved_skill_path']).read_text(encoding='utf-8')
        return {'skill_id': skill_id, 'body': text, 'sha256': row['actual_skill_sha256'],
                'license': row.get('license'), 'upstream_commit_sha': row.get('upstream_commit_sha')}
    raise DevelopmentSkillError('DEVELOPMENT_SKILL_NOT_FOUND', f'未找到开发 Skill：{skill_id}')
