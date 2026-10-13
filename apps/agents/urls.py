from django.urls import path
from apps.agents import views
app_name='agents'
urlpatterns=[path('api/v1/analytics/agent-traces/',views.traces,name='traces'),path('api/v1/analytics/agent-traces/<uuid:trace_id>/',views.trace_detail,name='trace_detail')]
