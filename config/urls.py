from django.contrib import admin
from django.urls import path,include
from core import views as core_views
from apps.accounts import views as accounts
from apps.knowledge import views as knowledge
from apps.knowledge import views_evidence as evidence
from apps.tutor import views as tutor
from apps.analytics import views as analytics
from apps.problems.urls import api_patterns as problem_api
from apps.learning.urls import api_patterns as learning_api
from apps.graph.urls import api_patterns as graph_api
from apps.graph.views import visualization
from apps.platform.urls import api_patterns as platform_api
from apps.workspace.urls import api_patterns as workspace_api

urlpatterns=[
 path('admin/',admin.site.urls),
 path('',core_views.dashboard,name='dashboard'),
 path('accounts/',include('apps.accounts.urls')),
 path('knowledge/',include('apps.knowledge.urls')),
 path('platform/',include('apps.platform.urls')),
 path('workbench/',include('apps.workspace.urls')),
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
 # EvidenceRAG Studio: additive maintenance API. All writes require staff and CSRF.
 path('api/v1/knowledge/tree/',evidence.tree),
 path('api/v1/knowledge/documents/upload/',evidence.upload_document),
 path('api/v1/knowledge/documents/<int:document_id>/',evidence.document_detail),
 path('api/v1/knowledge/documents/<int:document_id>/reindex/',evidence.reindex_document_api),
 path('api/v1/knowledge/chunks/<str:chunk_id>/restore/',evidence.chunk_restore),
 path('api/v1/knowledge/chunks/<str:chunk_id>/',evidence.chunk_dispatch),
 path('api/v1/knowledge/traces/<str:trace_id>/',evidence.trace_detail),
 path('api/v1/knowledge/conflicts/<str:conflict_id>/',evidence.conflict_detail),
 path('api/v1/knowledge/media/<str:asset_id>/file/',evidence.media_file),
 path('api/v1/analytics/agent-traces/',analytics.traces),
 path('api/v1/',include(problem_api+learning_api+graph_api+platform_api+workspace_api)),
]
