"""Create isolated demo workspaces for an existing account.

Never creates a fixed password and never touches a learner's private workspace.
Re-running is idempotent: existing demo spaces with documents are left as-is.
"""

from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from apps.knowledge.services.advanced_index_service import ingest_advanced

from apps.workspace.models import Workspace, WorkspaceDocument
from apps.workspace.services.workspaces import ensure_shared_course_workspace, serialize_workspace


DEMO_SPACES = (
    ('资料问答示例', 'generic', ('notes/learning_notes.md',)),
    ('文献比较示例', 'research_literature', (
        'research/paper_a.md', 'research/paper_b.md', 'research/paper_c.md',
    )),
    ('代码分析示例', 'software_engineering', (
        'code/inventory.py', 'code/inventory_check_demo.py',
    )),
)


class Command(BaseCommand):
    help = 'Seed isolated workbench demo spaces for an existing account.'

    def add_arguments(self, parser):
        parser.add_argument('--username', default='demo_student', help='Existing account name.')
        parser.add_argument('--force', action='store_true', help='Re-ingest files even if the demo space has documents.')

    def handle(self, *args, **options):
        User = get_user_model()
        user = User.objects.filter(username=options['username'], is_active=True).first()
        if user is None:
            fallback = User.objects.filter(is_staff=True, is_active=True).order_by('pk').first()
            if fallback is None:
                raise CommandError('未找到演示账户；请先创建账户，再用 --username 指定。')
            self.stdout.write(self.style.WARNING(
                f"账号 {options['username']} 不存在，改用管理员 {fallback.username}。"
            ))
            user = fallback
        shared = ensure_shared_course_workspace()
        if shared:
            self.stdout.write(f'共享课程空间：{shared[0].pk}，新链接 {shared[1]} 份文档。')
        base = Path(settings.BASE_DIR) / 'knowledge/workspace_demo'
        created = 0
        for name, domain, files in DEMO_SPACES:
            workspace, _ = Workspace.objects.get_or_create(
                owner=user, name=name, defaults={
                    'domain_pack_id': domain,
                    'description': '演示空间：可删除或自行修改，不影响其他用户。',
                    'visibility': 'private',
                },
            )
            existing = WorkspaceDocument.objects.filter(workspace=workspace).count()
            if existing and not options['force']:
                self.stdout.write(f'{name}: 已有 {existing} 份资料，跳过。')
                continue
            for relative in files:
                path = base / relative
                if not path.is_file():
                    raise CommandError(f'缺少演示文件：{path}')
                outcome = ingest_advanced(path, rebuild=False, index=True, workspace=workspace)
                document = outcome['document']
                warning = outcome.get('warning') or ''
                WorkspaceDocument.objects.update_or_create(
                    workspace=workspace, document=document,
                    defaults={
                        'added_by': user,
                        'original_name': document.name,
                        'file_path': document.path,
                        'status': 'partial' if warning or document.ingestion_status == 'partial' else 'ready',
                        'error_message': warning,
                    },
                )
                created += 1
            self.stdout.write(self.style.SUCCESS(
                f'{name}: {len(files)} 份资料，domain={workspace.domain_pack_id}'
            ))
        for workspace in Workspace.objects.filter(owner=user).order_by('pk'):
            self.stdout.write(f'  workspace {workspace.pk}: {serialize_workspace(user, workspace)["name"]}')
        self.stdout.write(self.style.SUCCESS(f'完成：新增/更新 {created} 份演示资料。'))
