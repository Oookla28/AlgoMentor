from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from apps.learning.services.progress_service import get_learning_summary
from apps.learning.services.recommendation_service import get_recommendations
from apps.learning.models import LearningActivity,MasteryState
from apps.knowledge.models import KnowledgePoint

@login_required
def dashboard(request):
    from django.utils import timezone
    summary=get_learning_summary(request.user,days=timezone.localdate().weekday()+1)
    summary['weekly_submissions']=summary['total_submissions']
    summary['total_points']=KnowledgePoint.objects.count()
    states=summary['knowledge_mastery']
    chapters=[]
    for n,name in enumerate(['绪论','线性表','栈与队列','串、数组和广义表'],1):
        rows=[s for s in states if s['chapter']==n]
        chapters.append({'name':name,'mastery':round(sum(s['index'] for s in rows)/len(rows),1) if rows else 0,'covered':sum(s['evidence_count']>0 for s in rows),'total':len(rows)})
    return render(request,'dashboard/index.html',{'summary':summary,'recommendations':get_recommendations(request.user),'recent_activities':LearningActivity.objects.filter(user=request.user).select_related('knowledge_point','submission').order_by('-created_at')[:6],'mastery_states':MasteryState.objects.filter(user=request.user).select_related('knowledge_point'),'chapters':chapters,'page_title':'学习总览'})
