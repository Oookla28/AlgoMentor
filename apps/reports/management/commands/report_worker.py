import os,signal,subprocess,sys,time
from django.conf import settings
from django.core.management.base import BaseCommand
from apps.reports.services.report_service import claim_next_task,fail_task,expire_tasks

class Command(BaseCommand):
    help='SQLite 持久化报告队列 Worker；每个任务在可强制终止的独立进程运行。'
    def add_arguments(self,parser):
        parser.add_argument('--once',action='store_true',help='处理最多一个任务后退出')
    def handle(self,*args,**options):
        self.stdout.write('报告 Worker 已启动。')
        try:
            while True:
                task=claim_next_task()
                if not task:
                    if options['once']: return
                    time.sleep(1);continue
                command=[sys.executable,str(settings.BASE_DIR/'manage.py'),'run_report_task','--task',str(task.pk)]
                env=os.environ.copy();env['CREWAI_TELEMETRY_DISABLED']='true';env['OTEL_SDK_DISABLED']='true'
                process=subprocess.Popen(command,cwd=str(settings.BASE_DIR),env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
                try:
                    process.wait(timeout=getattr(settings,'REPORT_TIMEOUT',120))
                    task.refresh_from_db()
                    if task.status=='RUNNING': fail_task(task.pk,'REPORT_WORKER_EXIT','报告子进程未返回有效结果。')
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid,signal.SIGKILL);process.wait()
                    fail_task(task.pk,'REPORT_TIMEOUT','报告生成已超时，请重试。',status='TIMEOUT')
                except KeyboardInterrupt:
                    os.killpg(process.pid,signal.SIGTERM);process.wait(timeout=5)
                    fail_task(task.pk,'REPORT_WORKER_STOPPED','报告 Worker 已停止，请重试。')
                    return
                if options['once']: return
        except KeyboardInterrupt:
            self.stdout.write('报告 Worker 已停止。')
