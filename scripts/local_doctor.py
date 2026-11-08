#!/usr/bin/env python3
"""Local deployment diagnostics. No network calls, no model downloads."""

import argparse
import json
import os
from pathlib import Path
import socket
import sys

DEFAULT_DEPLOY = Path('/Volumes/半岛铁盒/实验室考核部署')
RUNTIME_PATH = Path('/Volumes/半岛铁盒/实验室/runtime')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--deploy-dir', default=str(DEFAULT_DEPLOY))
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args()
    target = Path(args.deploy_dir).resolve()
    if not (target / 'manage.py').is_file():
        print(f'FAIL 部署目录无效：{target}', file=sys.stderr)
        return 2
    if RUNTIME_PATH.is_dir() and str(RUNTIME_PATH) not in sys.path:
        sys.path.insert(0, str(RUNTIME_PATH))
    sys.path.insert(0, str(target))
    os.chdir(target)
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')
    import django
    django.setup()

    from django.conf import settings
    from django.db import connection
    from django.db.migrations.loader import MigrationLoader
    from apps.knowledge.models import KnowledgeDocument
    from apps.platform.capabilities import probe_capabilities
    from apps.platform.models import AgentRun
    from apps.platform.skills import skills_health
    from apps.workspace.models import Workspace, WorkspaceDocument
    from apps.workspace.services.tasks import worker_status

    checks = []

    def add(state, name, detail=''):
        checks.append({'state': state, 'name': name, 'detail': str(detail)})

    db_path = Path(settings.DATABASES['default']['NAME'])
    try:
        with connection.cursor() as cursor:
            cursor.execute('PRAGMA quick_check')
            check = cursor.fetchone()
        add('PASS' if check and check[0] == 'ok' else 'WARN', 'database', check[0] if check else 'no result')
    except Exception as exc:
        add('FAIL', 'database', type(exc).__name__)
    add('PASS' if db_path.exists() else 'FAIL', 'database_file', db_path)
    if db_path.exists():
        add('PASS' if os.access(db_path, os.W_OK) else 'FAIL', 'database_writable', db_path)

    try:
        loader = MigrationLoader(connection, ignore_no_migrations=True)
        unapplied = sorted(
            f'{app}.{name}'
            for app, name in (set(loader.disk_migrations) - set(loader.applied_migrations))
        )
        add('PASS' if not unapplied else 'FAIL', 'migrations', unapplied[:10] or 'up to date')
    except Exception as exc:
        add('FAIL', 'migrations', type(exc).__name__)

    chroma = Path(os.getenv('CHROMA_PATH', str(settings.CHROMA_PATH)))
    try:
        chroma.mkdir(parents=True, exist_ok=True)
        probe = chroma / '.doctor_write_test'
        probe.write_text('ok', encoding='utf-8')
        probe.unlink(missing_ok=True)
        add('PASS', 'chroma_writable', chroma)
    except Exception as exc:
        add('FAIL', 'chroma_writable', f'{chroma} ({type(exc).__name__})')

    for relative in ('static/css/app.css', 'static/css/workbench.css', 'templates/workbench/index.html', 'agent_skills/registry.json'):
        add('PASS' if (target / relative).is_file() else 'FAIL', 'asset', relative)

    try:
        add('PASS', 'documents', {
            'total': KnowledgeDocument.objects.count(),
            'advanced': KnowledgeDocument.objects.exclude(latest_index_version='').count(),
        })
        add('PASS', 'workspaces', {
            'total': Workspace.objects.count(),
            'documents': WorkspaceDocument.objects.count(),
            'ready': WorkspaceDocument.objects.filter(status='ready').count(),
            'partial': WorkspaceDocument.objects.filter(status='partial').count(),
            'failed': WorkspaceDocument.objects.filter(status='failed').count(),
        })
        add('PASS', 'tasks', {
            status: AgentRun.objects.filter(status=status).count()
            for status in ('QUEUED', 'RUNNING', 'SUCCEEDED', 'PARTIAL', 'ABSTAINED', 'FAILED', 'CANCELLED')
        })
    except Exception as exc:
        add('FAIL', 'database_counts', type(exc).__name__)

    worker = worker_status()
    add('PASS' if worker['online'] else 'WARN', 'worker', worker)
    skills = skills_health()
    add('PASS' if skills['state'] == 'available' else 'WARN', 'skills', {
        'state': skills['state'], 'available': skills.get('available', 0), 'failed': skills.get('failed', 0),
    })

    port = int(os.getenv('DEPLOY_PORT', '8010'))
    port_file = target / 'data/run/port.txt'
    if port_file.is_file():
        try:
            port = int(port_file.read_text().strip())
        except ValueError:
            pass
    try:
        with socket.create_connection(('127.0.0.1', port), timeout=1):
            add('PASS', 'web_port', f'127.0.0.1:{port} open')
    except OSError:
        add('WARN', 'web_port', f'127.0.0.1:{port} closed (run local_start.sh)')

    capabilities = {item['name']: item['state'] for item in probe_capabilities()}
    add('INFO', 'capabilities', capabilities)

    if args.json:
        print(json.dumps(checks, ensure_ascii=False, indent=2))
    else:
        for check in checks:
            print(f"{check['state']:4} {check['name']:20} {check['detail']}")
    fatal = [check for check in checks if check['state'] == 'FAIL']
    return 1 if fatal else 0


if __name__ == '__main__':
    raise SystemExit(main())
