from django.contrib.auth.decorators import login_required
from django.shortcuts import render,get_object_or_404
from core.http import api_endpoint
from apps.reports.models import LearningReport,ReportTask
from apps.reports.services.statistics_service import weekly_statistics
from apps.reports.services.report_service import enqueue_report,report_status,serialize_report,expire_tasks

@login_required
def index(request):
    expire_tasks()
    return render(request,'reports/index.html',{'reports':LearningReport.objects.filter(user=request.user)[:20],'tasks':ReportTask.objects.filter(user=request.user)[:10],'statistics':weekly_statistics(request.user)})

@login_required
def detail(request,report_id):
    return render(request,'reports/detail.html',{'report':get_object_or_404(LearningReport,pk=report_id,user=request.user)})

@api_endpoint(methods=('POST',))
def create_report(request):
    task=enqueue_report(request.user)
    return report_status(request.user,task.pk)

@api_endpoint()
def task_status(request,task_id):
    return report_status(request.user,task_id)

@api_endpoint()
def report_detail(request,report_id):
    return serialize_report(LearningReport.objects.get(pk=report_id,user=request.user))
