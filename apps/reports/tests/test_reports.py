import os
os.environ.setdefault('OTEL_SDK_DISABLED','true');os.environ.setdefault('CREWAI_TELEMETRY_DISABLED','true')
import json
from datetime import timedelta
from unittest.mock import Mock,patch
from cryptography.fernet import Fernet
from django.contrib.auth.models import User
from django.utils import timezone
import pytest
from crewai import BaseLLM
from apps.accounts.services.credential_service import save_config
from apps.reports.models import LearningReport,ReportTask
from apps.reports.services.statistics_service import weekly_statistics,validated_metrics
from apps.reports.services.crew_service import ReportNarrative,generate_learning_report,validate_narrative,GeneratedReport
from apps.reports.services.report_service import enqueue_report,claim_next_task,publish_result,expire_tasks,report_status
from core.exceptions import BusinessError

pytestmark=pytest.mark.django_db(transaction=True)

@pytest.fixture
def user(settings):
    settings.APP_ENCRYPTION_KEY=Fernet.generate_key().decode()
    student=User.objects.create_user('reportstudent');save_config(student,'sk-test-key-12345678');return student


def narrative(stats,**kwargs):
    value={'metrics':validated_metrics(stats),'learning_overview':'当前学习记录不足，应开始系统练习。','daily_trend_analysis':'当前没有学习趋势证据。','knowledge_performance':'知识点掌握情况尚需练习证据。','mistake_analysis':'没有错题记录。','graph_change_analysis':'没有图谱变化记录。','progress_analysis':'尚无进步证据。','weak_points_analysis':'缺少学习证据，不能判断薄弱点。','next_week_suggestions':['从线性表基础练习开始。']}
    value.update(kwargs);return ReportNarrative(**value)


def test_statistics_empty_is_not_fake(user):
    stats=weekly_statistics(user)
    assert stats['total_submissions']==0 and stats['accuracy'] is None and not stats['weak_points']
    assert all(point['evidence_count']==0 for point in stats['knowledge_mastery'])


def test_real_crewai_sequential_two_agents_two_tasks_with_injected_llm(user):
    stats=weekly_statistics(user);doc=narrative(stats)
    class TestLLM(BaseLLM):
        def __init__(self): super().__init__(model='test-only');self.calls=0
        def call(self,messages,**kwargs):
            self.calls+=1
            return 'Final Answer: 当前缺少学习记录，建议开始基础练习。' if self.calls==1 else 'Final Answer: '+doc.model_dump_json()
        def supports_function_calling(self): return False
    llm=TestLLM()
    result=generate_learning_report(user.pk,authorized_user=user,statistics=stats,llm=llm)
    assert llm.calls==2
    assert result.statistics==stats and '# 本周学习报告' in result.markdown
    assert '| 有效提交次数 | 0 |' in result.markdown
    assert '暂无有效提交' in result.markdown


def test_numeric_mismatch_is_rejected(user):
    stats=weekly_statistics(user);doc=narrative(stats);doc.metrics['total_submissions']=999
    with pytest.raises(BusinessError) as exc: validate_narrative(doc,stats)
    assert exc.value.code=='REPORT_NUMERIC_MISMATCH'
    with pytest.raises(BusinessError) as exc: validate_narrative(narrative(stats,progress_analysis='完成 99 题。'),stats)
    assert exc.value.code=='REPORT_UNVERIFIED_NUMBER'


def test_other_student_report_not_accessible(user,client):
    task=enqueue_report(user)
    other=User.objects.create_user('reportother');client.force_login(other)
    assert client.get(f'/api/v1/reports/{task.pk}/status/').status_code==404
    with pytest.raises(BusinessError): generate_learning_report(user.pk,authorized_user=other)


def test_persisted_task_and_publish(user):
    task=enqueue_report(user);assert task.status=='PENDING'
    assert enqueue_report(user).pk==task.pk
    claimed=claim_next_task();assert claimed.pk==task.pk and claimed.status=='RUNNING'
    result=GeneratedReport('实际测试报告',task.statistics,'deepseek-flash')
    assert publish_result(task.pk,result)
    state=report_status(user,task.pk)
    assert state['status']=='SUCCESS' and state['report']['validated']
    assert LearningReport.objects.get().statistics==task.statistics


def test_running_timeout_and_late_result_rejected(user):
    task=enqueue_report(user);claim_next_task()
    ReportTask.objects.filter(pk=task.pk).update(deadline_at=timezone.now()-timedelta(seconds=1))
    expire_tasks();task.refresh_from_db();assert task.status=='TIMEOUT'
    assert not publish_result(task.pk,GeneratedReport('迟到结果',task.statistics,'deepseek-flash'))
    assert not LearningReport.objects.exists()


def test_worker_timeout_state_with_injected_process(user,settings):
    from django.core.management import call_command
    import subprocess
    task=enqueue_report(user);settings.REPORT_TIMEOUT=1
    process=Mock(pid=123);process.wait.side_effect=[subprocess.TimeoutExpired('worker',1),0]
    with patch('apps.reports.management.commands.report_worker.subprocess.Popen',return_value=process),patch('apps.reports.management.commands.report_worker.os.killpg') as kill:
        call_command('report_worker',once=True)
    task.refresh_from_db();assert task.status=='TIMEOUT'
    kill.assert_called_once()


def test_queue_missing_worker_expiry(user):
    task=enqueue_report(user)
    ReportTask.objects.filter(pk=task.pk).update(created_at=timezone.now()-timedelta(hours=25))
    expire_tasks();task.refresh_from_db();assert task.status=='FAILED' and task.error_code=='REPORT_WORKER_UNAVAILABLE'


def test_worker_really_kills_hung_child_process(user,settings):
    from django.core.management import call_command
    import subprocess,sys
    task=enqueue_report(user);settings.REPORT_TIMEOUT=1
    original=subprocess.Popen;children=[]
    def start_child(*args,**kwargs):
        process=original([sys.executable,'-c','import time;time.sleep(30)'],**kwargs)
        children.append(process);return process
    with patch('apps.reports.management.commands.report_worker.subprocess.Popen',side_effect=start_child):
        call_command('report_worker',once=True)
    task.refresh_from_db()
    assert task.status=='TIMEOUT' and children[0].poll() is not None


def test_publish_rejects_changed_snapshot(user):
    task=enqueue_report(user);claim_next_task()
    altered={**task.statistics,'total_submissions':99}
    with pytest.raises(BusinessError) as exc: publish_result(task.pk,GeneratedReport('不一致',altered,'deepseek-flash'))
    assert exc.value.code=='REPORT_SNAPSHOT_MISMATCH'
    assert not LearningReport.objects.exists()
