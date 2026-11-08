from django.urls import path

from . import views

app_name = 'platform'

api_patterns = [
    path('platform/capabilities/', views.capabilities_api, name='capabilities'),
    path('platform/domains/', views.domains_api, name='domains'),
    path('platform/agent/run/', views.agent_run_api, name='agent_run'),
    path('platform/runs/', views.runs_api, name='runs'),
    path('platform/runs/<str:run_id>/', views.run_detail_api, name='run_detail'),
    path('platform/domains/sync/', views.sync_domains_api, name='sync_domains'),
]

urlpatterns = [
    path('', views.console, name='console'),
]
