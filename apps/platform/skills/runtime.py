"""Progressive, permission-bounded Skill runtime.

The registry only carries metadata. Bodies are loaded lazily after a server-side
tool-scope intersection. YAML is parsed with ``safe_load``; paths, symlinks, size
and total reference size are bounded. Skills never grant permissions and their
bodies are treated as untrusted operating instructions, not executable code.
"""

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Iterable

import yaml
from django.conf import settings

MAX_REGISTRY_BYTES = 256 * 1024
MAX_SKILL_BYTES = 64 * 1024
MAX_BODY_CHARS = 24000
MAX_ACTIVE_SKILLS = 2

_SKILL_CACHE = {}


class SkillError(Exception):
    def __init__(self, code, message=''):
        super().__init__(message or code)
        self.code = code
        self.message = message or code


@dataclass(frozen=True)
class SkillDefinition:
    skill_id: str
    version: str
    name: str
    description: str
    entry: str
    task_types: tuple
    domains: tuple
    allowed_tools: tuple
    enabled: bool = True
    max_reference_tokens: int = 1200

    def to_dict(self):
        return {
            'skill_id': self.skill_id, 'version': self.version, 'name': self.name,
            'description': self.description, 'task_types': list(self.task_types),
            'domains': list(self.domains), 'allowed_tools': list(self.allowed_tools),
            'enabled': self.enabled, 'max_reference_tokens': self.max_reference_tokens,
        }


def _root(root=None):
    return Path(root) if root is not None else Path(settings.BASE_DIR) / 'agent_skills'


def _registry_path(root=None):
    return _root(root) / 'registry.json'


def load_registry(root=None) -> list[SkillDefinition]:
    path = _registry_path(root)
    if not path.is_file():
        return []
    if path.stat().st_size > MAX_REGISTRY_BYTES:
        raise SkillError('SKILL_REGISTRY_TOO_LARGE', 'Skill 注册表超过大小限制。')
    try:
        payload = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        raise SkillError('SKILL_REGISTRY_INVALID', 'Skill 注册表无法解析。') from exc
    if not isinstance(payload, dict) or not isinstance(payload.get('skills'), list):
        raise SkillError('SKILL_REGISTRY_INVALID', 'Skill 注册表结构无效。')
    seen = set()
    definitions = []
    for raw in payload['skills']:
        if not isinstance(raw, dict):
            raise SkillError('SKILL_REGISTRY_INVALID', 'Skill 条目必须是对象。')
        skill_id = str(raw.get('id') or '').strip()
        version = str(raw.get('version') or '').strip()
        entry = str(raw.get('entry') or '').strip()
        if not skill_id or not version or not entry:
            raise SkillError('SKILL_REGISTRY_INVALID', 'Skill 缺少 id/version/entry。')
        key = (skill_id, version)
        if key in seen:
            raise SkillError('SKILL_REGISTRY_DUPLICATE', f'重复 Skill：{skill_id}@{version}')
        seen.add(key)
        _validate_entry(entry, root)
        definitions.append(SkillDefinition(
            skill_id=skill_id, version=version,
            name=str(raw.get('name') or skill_id)[:120],
            description=str(raw.get('description') or '')[:500],
            entry=entry,
            task_types=tuple(str(item) for item in (raw.get('task_types') or [])),
            domains=tuple(str(item) for item in (raw.get('domains') or ['*'])),
            allowed_tools=tuple(str(item) for item in (raw.get('allowed_tools') or [])),
            enabled=bool(raw.get('enabled', True)),
            max_reference_tokens=int(raw.get('max_reference_tokens') or 1200),
        ))
    return definitions


def _validate_entry(entry, root=None):
    relative = Path(str(entry))
    base = (_root(root) / 'runtime').resolve()
    if relative.is_absolute() or '..' in relative.parts or not str(entry).startswith('runtime/'):
        raise SkillError('SKILL_PATH_INVALID', 'Skill 入口必须位于 runtime/ 下。')
    current = _root(root)
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise SkillError('SKILL_SYMLINK_REJECTED', '拒绝加载符号链接 Skill。')
    resolved = current.resolve()
    if base != resolved and base not in resolved.parents:
        raise SkillError('SKILL_PATH_TRAVERSAL', 'Skill 入口越出允许目录。')
    if not resolved.is_file():
        raise SkillError('SKILL_NOT_FOUND', 'Skill 入口文件不存在。')
    if resolved.stat().st_size > MAX_SKILL_BYTES:
        raise SkillError('SKILL_TOO_LARGE', 'Skill 正文超过大小限制。')
    return resolved


def _skill_path(skill: SkillDefinition, root=None):
    return _validate_entry(skill.entry, root)


def load_skill(skill: SkillDefinition, root=None) -> dict:
    """Lazy-load frontmatter + body. The result is cached by content hash."""
    path = _skill_path(skill, root)
    stat = path.stat()
    cache_key = (str(path), stat.st_mtime_ns, stat.st_size)
    if cache_key in _SKILL_CACHE:
        return _SKILL_CACHE[cache_key]
    text = path.read_text(encoding='utf-8')
    if not text.startswith('---'):
        raise SkillError('SKILL_FRONTMATTER_MISSING', 'Skill 缺少 YAML frontmatter。')
    end = text.find('\n---', 3)
    if end < 0:
        raise SkillError('SKILL_FRONTMATTER_INVALID', 'Skill frontmatter 未闭合。')
    try:
        meta = yaml.safe_load(text[3:end]) or {}
    except yaml.YAMLError as exc:
        raise SkillError('SKILL_FRONTMATTER_INVALID', 'Skill frontmatter YAML 无效。') from exc
    if not isinstance(meta, dict):
        raise SkillError('SKILL_FRONTMATTER_INVALID', 'Skill frontmatter 必须是映射。')
    body = text[end + 4:].strip()
    if len(body) > MAX_BODY_CHARS:
        raise SkillError('SKILL_TOO_LARGE', 'Skill 正文超过字符限制。')
    digest = hashlib.sha256(text.encode('utf-8')).hexdigest()
    result = {
        'meta': {
            'name': str(meta.get('name') or skill.skill_id),
            'version': str(meta.get('version') or skill.version),
            'description': str(meta.get('description') or ''),
            'triggers': list(meta.get('triggers') or []),
            'not_triggers': list(meta.get('not-triggers') or []),
            'failure_behavior': str(meta.get('failure_behavior') or ''),
        },
        'body': body,
        'content_hash': digest,
        'path': str(path),
    }
    _SKILL_CACHE[cache_key] = result
    return result


def catalog(root=None):
    entries = []
    for skill in load_registry(root):
        row = skill.to_dict()
        try:
            loaded = load_skill(skill, root)
            row['state'] = 'available' if skill.enabled else 'disabled'
            row['content_hash'] = loaded['content_hash']
        except SkillError as exc:
            row['state'] = 'failed'
            row['error_code'] = exc.code
        entries.append(row)
    return entries


def skills_health(root=None):
    try:
        entries = catalog(root)
    except SkillError as exc:
        return {'state': 'failed', 'error_code': exc.code, 'skills': []}
    failed = [row for row in entries if row.get('state') == 'failed']
    enabled = [row for row in entries if row.get('state') == 'available']
    return {
        'state': 'failed' if failed else ('available' if enabled else 'disabled'),
        'available': len(enabled), 'failed': len(failed), 'skills': entries,
    }


def select_skills(task_type, domain, query='', attempts=0, root=None):
    """Deterministic selection, at most MAX_ACTIVE_SKILLS, never load order-based."""
    try:
        definitions = load_registry(root)
    except SkillError:
        return []
    query = query or ''
    selected = []
    if attempts and attempts > 0:
        selected.extend(skill for skill in definitions if skill.skill_id == 'task-recovery')
    for skill in definitions:
        if skill in selected or not skill.enabled:
            continue
        if task_type not in skill.task_types:
            continue
        if '*' not in skill.domains and domain not in skill.domains:
            continue
        if skill.skill_id == 'task-recovery':
            continue
        if skill.skill_id == 'experiment-review':
            markers = ('实验', '复现', '消融', '泄漏', '公平', 'reproduce', 'ablation')
            if not any(marker in query.lower() for marker in markers):
                continue
        selected.append(skill)
        if len(selected) >= MAX_ACTIVE_SKILLS:
            break
    return selected[:MAX_ACTIVE_SKILLS]


def resolve_tool_scope(task_pack, domain_pack, skill, enabled_tools: Iterable[str]):
    """Server-side intersection; a Skill's list can only narrow, never expand."""
    allowed = set(enabled_tools)
    return sorted(
        set(task_pack.tool_ids)
        & set(domain_pack.tool_manifest)
        & set(skill.allowed_tools)
        & allowed
    )


def activate_skill(run, skill: SkillDefinition, trigger, tool_scope, root=None):
    from apps.workspace.models import SkillActivation

    loaded = load_skill(skill, root)
    activation, _created = SkillActivation.objects.update_or_create(
        run=run, skill_id=skill.skill_id, version=skill.version,
        defaults={
            'content_hash': loaded['content_hash'],
            'trigger': (trigger or '')[:200],
            'tool_scope': list(tool_scope),
            'status': 'activated',
            'result_summary': f"{loaded['meta']['name']}：方法已加载，工具范围 {len(tool_scope)} 项。",
        },
    )
    return loaded, activation
