from django.urls import path
from apps.reports import views
app_name='reports'
urlpatterns=[path('reports/',views.index,name='index'),path('reports/<uuid:report_id>/',views.detail,name='detail'),path('api/report/',views.create_report,name='create_report'),path('api/v1/reports/',views.create_report,name='create'),path('api/v1/reports/<uuid:task_id>/status/',views.task_status,name='status'),path('api/v1/reports/<uuid:report_id>/',views.report_detail,name='api_detail')]
