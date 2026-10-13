from django.urls import path
from . import views
app_name = "problems"
urlpatterns = [path("problems/", views.problem_list, name="list"), path("problems/<slug:slug>/", views.problem_detail, name="detail"), path("lab/", views.lab, name="lab")]
api_patterns = [path("submissions/<int:submission_id>/diagnosis/", views.diagnosis_api), path("code/run/", views.code_run, name="code-run"), path("code/submit/", views.code_submit, name="code-submit"),
                path("submissions/<int:submission_id>/", views.submission_detail, name="submission-detail"),
                path("problems/<int:problem_id>/reference/", views.reference_solution, name="problem-reference")]
