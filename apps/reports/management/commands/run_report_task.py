import os
os.environ.setdefault('CREWAI_TELEMETRY_DISABLED','true')
os.environ.setdefault('OTEL_SDK_DISABLED','true')
from django.core.management.base import BaseCommand
from apps.reports.models import ReportTask
from apps.reports.services.crew_service import generate_learning_report
from apps.reports.services.report_service import publish_result,fail_task
from core.exceptions import BusinessError

class Command(BaseCommand):
    help='内部命令：在独立 Worker 子进程中运行已认领报告任务。'
    def add_arguments(self,parser): parser.add_argument('--task',required=True)
    def handle(self,*args,**options):
        task=ReportTask.objects.select_related('user').get(pk=options['task'],status='RUNNING')
        try:
            result=generate_learning_report(task.user_id,authorized_user=task.user,statistics=task.statistics,tier=task.tier)
            publish_result(task.pk,result)
        except BusinessError as exc:
            fail_task(task.pk,exc.code,exc.message,'TIMEOUT' if 'TIMEOUT' in exc.code else 'FAILED')
        except Exception as exc:
            fail_task(task.pk,type(exc).__name__,'报告生成失败，请检查 AI 配置和服务状态。')
