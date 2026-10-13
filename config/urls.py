from django.contrib import admin
from django.urls import path,include
from core import views as core_views
from apps.accounts import views as accounts
from apps.knowledge import views as knowledge
from apps.tutor import views as tutor
from apps.analytics import views as analytics
from apps.problems.urls import api_patterns as problem_api
from apps.learning.urls import api_patterns as learning_api
from apps.graph.urls import api_patterns as graph_api
from apps.graph.views import visualization

urlpatterns=[
 path('admin/',admin.site.urls),
 path('',core_views.dashboard,name='dashboard'),
 path('accounts/',include('apps.accounts.urls')),
 path('knowledge/',include('apps.knowledge.urls')),
 path('tutor/',include('apps.tutor.urls')),
 path('',include('apps.problems.urls')),
 path('',include('apps.learning.urls')),
 path('',include('apps.graph.urls')),
 path('',include('apps.reports.urls')),
 path('visualizations/',visualization,name='visualization'),
 path('api/settings/deepseek/test/',accounts.test_connection),
 path('api/v1/ai/config/',accounts.ai_config),
 path('api/v1/ai/test/',accounts.test_connection),
 path('api/v1/ai/models/',accounts.ai_models),
 path('api/v1/services/status/',core_views.service_statuses),
 path('api/chat/',tutor.chat_api),
 path('api/v1/chat/',tutor.chat_api),
 path('api/v1/chat/sessions/',tutor.sessions_api),
 path('api/v1/chat/sessions/<int:session_id>/',tutor.session_api),
 path('api/v1/chat/sessions/<int:session_id>/teaching/',tutor.teaching_api),
 path('api/v1/knowledge/search/',knowledge.search),
 path('api/v1/knowledge/local/',knowledge.local_search),
 path('api/v1/knowledge/wikipedia/',knowledge.wikipedia_search),
 path('api/v1/knowledge/points/',knowledge.points_api),
 path('api/v1/analytics/agent-traces/',analytics.traces),
 path('api/v1/',include(problem_api+learning_api+graph_api)),
]
