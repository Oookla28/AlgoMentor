from django.urls import path
from . import views
app_name='knowledge'
urlpatterns=[path('',views.index,name='index'),path('local/',views.local_learning,name='local'),path('wikipedia/',views.wikipedia_page,name='wikipedia'),path('source/<str:chunk_id>/',views.source,name='source')]
