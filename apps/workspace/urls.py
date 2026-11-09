from django.urls import path

from . import views

app_name = 'workspace'

api_patterns = [
    path('workbench/workspaces/', views.workspaces_api, name='workspaces'),
    path('workbench/workspaces/<int:workspace_id>/', views.workspace_detail_api, name='workspace_detail'),
    path('workbench/workspaces/<int:workspace_id>/documents/', views.upload_document_api, name='upload_document'),
    path('workbench/workspaces/<int:workspace_id>/documents/<int:document_id>/action/', views.document_action_api, name='document_action'),
    path('workbench/tasks/', views.tasks_api, name='tasks'),
    path('workbench/tasks/<str:run_id>/', views.task_detail_api, name='task_detail'),
    path('workbench/tasks/<str:run_id>/action/', views.task_action_api, name='task_action'),
    path('workbench/literature/recommendations/', views.literature_recommendations_api, name='literature_recommendations'),
    path('workbench/status/', views.status_api, name='status'),
]

urlpatterns = [
    path('', views.workbench, name='index'),
    path('artifacts/<str:artifact_id>/download/', views.artifact_download, name='artifact_download'),
]
