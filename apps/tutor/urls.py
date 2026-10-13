from django.urls import path
from . import views
app_name='tutor'
urlpatterns=[path('',views.chat,name='chat')]
