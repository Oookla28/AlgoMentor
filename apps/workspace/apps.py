from django.apps import AppConfig


class WorkspaceConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.workspace'
    label = 'workspace'
    verbose_name = '私有工作空间与任务产物'
