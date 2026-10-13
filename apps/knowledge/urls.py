from django.urls import path
from . import views
app_name='knowledge'
urlpatterns=[path('',views.index,name='index'),path('source/<str:chunk_id>/',views.source,name='source')]
