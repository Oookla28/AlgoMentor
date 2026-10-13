from django.urls import path
from . import views
app_name = "graph"
urlpatterns = [path("graph/", views.index, name="index"), path("visualization/", views.visualization, name="visualization")]
api_patterns = [path("graph/", views.graph_api), path("graph/nodes/<slug:slug>/", views.node_api), path("graph/progress/", views.progress_api),
                path("graph/path/", views.path_api), path("algorithms/steps/", views.algorithm_api)]
