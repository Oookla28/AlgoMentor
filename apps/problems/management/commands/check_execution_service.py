"""Verify an isolated execution service with one harmless, fixed Python program."""
from django.core.management.base import BaseCommand, CommandError
from core.exceptions import CodeExecutionError
from core.execution.provider import get_execution_provider


class Command(BaseCommand):
    help = '发送固定 print 程序，验证执行能力；不把语言列表成功等同于可执行。'

    def handle(self, *args, **options):
        try:
            result = get_execution_provider().run("print('ALGOMENTOR_EXECUTION_READY')")
        except CodeExecutionError as exc:
            raise CommandError(f'{exc.code}: {exc.message}') from None
        if result.status != 'ACCEPTED' or result.stdout.strip() != 'ALGOMENTOR_EXECUTION_READY':
            raise CommandError('服务未返回正确的实际执行结果；不能标记连接成功。')
        self.stdout.write(self.style.SUCCESS(f'真实执行通过：{result.provider}，耗时 {result.elapsed_seconds:.3f} 秒。'))
