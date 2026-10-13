from django.urls import path
from django.contrib.auth import views as auth_views
from apps.accounts import views
app_name = 'accounts'
urlpatterns = [
    path('register/',views.register,name='register'),
    path('login/',auth_views.LoginView.as_view(template_name='accounts/login.html'),name='login'),
    path('logout/',auth_views.LogoutView.as_view(),name='logout'),
    path('settings/',views.settings_page,name='settings'),
    path('api/v1/ai/config/',views.ai_config,name='ai_config'),
    path('api/v1/ai/test/',views.test_connection,name='ai_test'),
    path('api/settings/deepseek/test/',views.test_connection,name='deepseek_test'),
    path('api/v1/ai/models/',views.ai_models,name='ai_models'),
]
