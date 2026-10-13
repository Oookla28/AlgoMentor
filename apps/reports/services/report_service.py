import json
from datetime import timedelta
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from apps.accounts.services.credential_service import get_api_key,get_config
from apps.reports.models import ReportTask,LearningReport
from apps.reports.services.statistics_service import weekly_statistics
from core.security.permissions import require_user
from core.exceptions import BusinessError


def expire_tasks():
    now=timezone.now()
    ReportTask.objects.filter(status='RUNNING',deadline_at__lt=now).update(status='TIMEOUT',finished_at=now,error_code='REPORT_TIMEOUT',error_message='报告生成已超时，请重试。')
    ReportTask.objects.filter(status='PENDING',created_at__lt=now-timedelta(hours=24)).update(status='FAILED',finished_at=now,error_code='REPORT_WORKER_UNAVAILABLE',error_message='报告队列等待超时，请联系管理员启动报告 Worker。')


@transaction.atomic
def enqueue_report(user) -> ReportTask:
    require_user(user);get_api_key(user)
    from core.services.availability import ServiceAvailabilityManager
    from core.llm.model_registry import get_tier
    tier = get_config(user).default_tier
    if not ServiceAvailabilityManager('deepseek', user=user, model=get_tier(tier).model).can_attempt():
        raise BusinessError('DeepSeek 暂不可用，智能报告尚未生成。学习统计与历史报告仍可查看；稍后重试。',
                            code='DEEPSEEK_TEMPORARILY_UNAVAILABLE', status_code=503)
    expire_tasks()
    existing=ReportTask.objects.filter(user=user,status__in=['PENDING','RUNNING']).first()
    if existing: return existing
    if ReportTask.objects.filter(user=user,created_at__gte=timezone.now()-timedelta(minutes=5)).count()>=3:
        raise BusinessError('报告请求过于频繁，请稍后再试。',code='REPORT_RATE_LIMITED',status_code=429)
    return ReportTask.objects.create(user=user,tier=tier,statistics=weekly_statistics(user))


def claim_next_task():
    expire_tasks()
    for task in ReportTask.objects.filter(status='PENDING').order_by('created_at')[:10]:
        now=timezone.now()
        changed=ReportTask.objects.filter(pk=task.pk,status='PENDING').update(status='RUNNING',started_at=now,deadline_at=now+timedelta(seconds=getattr(settings,'REPORT_TIMEOUT',120)))
        if changed:
            task.refresh_from_db();return task
    return None


def serialize_report(report):
    return {'id':str(report.pk),'markdown':report.markdown,'statistics':report.statistics,'created_at':report.created_at.isoformat(),'selected_model':report.selected_model,'validated':report.validated,'url':f'/reports/{report.pk}/'}


def report_status(user,task_id):
    expire_tasks()
    task=ReportTask.objects.select_related('report').get(pk=task_id,user=require_user(user))
    result={'id':str(task.pk),'status':task.status,'error_code':task.error_code,'error_message':task.error_message,'status_url':f'/api/v1/reports/{task.pk}/status/'}
    if task.report_id: result['report']=serialize_report(task.report)
    return result


@transaction.atomic
def publish_result(task_id,result):
    task=ReportTask.objects.select_for_update().get(pk=task_id)
    if task.status!='RUNNING' or (task.deadline_at and task.deadline_at<timezone.now()):
        return False
    if json.dumps(result.statistics,sort_keys=True) != json.dumps(task.statistics,sort_keys=True):
        raise BusinessError('报告统计与任务快照不一致。',code='REPORT_SNAPSHOT_MISMATCH')
    report=LearningReport.objects.create(user=task.user,period_start=task.statistics['period_start'],period_end=task.statistics['period_end'],statistics=result.statistics,markdown=result.markdown,selected_model=result.model,validated=True)
    task.report=report;task.status='SUCCESS';task.finished_at=timezone.now();task.save(update_fields=['report','status','finished_at'])
    return True


def fail_task(task_id,code,message,status='FAILED'):
    ReportTask.objects.filter(pk=task_id,status='RUNNING').update(status=status,error_code=code[:80],error_message=message[:500],finished_at=timezone.now())
