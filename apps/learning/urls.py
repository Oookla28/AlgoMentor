from django.urls import path
from . import views
app_name = "learning"
urlpatterns = [path("learning/", views.overview, name="overview"), path("mistakes/", views.mistakes, name="mistakes")]
api_patterns = [path("learning/summary/", views.summary_api), path("learning/mistakes/", views.mistakes_api),
                path("learning/mistakes/<int:mistake_id>/review/", views.review_api), path("learning/recommendations/", views.recommendations_api)]
