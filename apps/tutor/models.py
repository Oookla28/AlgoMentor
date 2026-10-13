from django.conf import settings
from django.db import models

class ChatSession(models.Model):
    user=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.CASCADE,related_name='chat_sessions')
    title=models.CharField(max_length=100,default='新学习会话')
    created_at=models.DateTimeField(auto_now_add=True)
    updated_at=models.DateTimeField(auto_now=True)
    class Meta: ordering=['-updated_at']

class ChatMessage(models.Model):
    session=models.ForeignKey(ChatSession,on_delete=models.CASCADE,related_name='messages')
    role=models.CharField(max_length=20,choices=[('user','学生'),('assistant','助教')])
    content=models.TextField()
    citations=models.JSONField(default=list)
    trace_id=models.CharField(max_length=100,blank=True)
    status=models.CharField(max_length=20,default='SUCCESS')
    created_at=models.DateTimeField(auto_now_add=True)
    class Meta: ordering=['created_at','id']

class TeachingSession(models.Model):
    user=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.CASCADE)
    chat_session=models.OneToOneField(ChatSession,on_delete=models.CASCADE,related_name='teaching')
    problem=models.ForeignKey('problems.Problem',on_delete=models.SET_NULL,null=True,blank=True)
    knowledge_point=models.ForeignKey('knowledge.KnowledgePoint',on_delete=models.SET_NULL,null=True,blank=True)
    teaching_mode=models.CharField(max_length=20,default='explain')
    current_level=models.PositiveSmallIntegerField(default=1)
    current_objective=models.CharField(max_length=255,blank=True)
    provided_hints=models.JSONField(default=list)
    last_student_response=models.TextField(blank=True)
    current_status=models.CharField(max_length=20,default='ACTIVE')
