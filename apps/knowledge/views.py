from django.shortcuts import render,get_object_or_404
from django.contrib.auth.decorators import login_required
from core.http import api_endpoint
from .models import KnowledgePoint,KnowledgeDocument,KnowledgeChunk,KnowledgeCorrection
from .services.retrieval_service import retrieve_knowledge,citations_json

@login_required
def index(request):
    points=KnowledgePoint.objects.all()
    if request.GET.get('chapter','').isdigit(): points=points.filter(chapter=int(request.GET['chapter']))
    return render(request,'knowledge/index.html',{'points':points,'documents':KnowledgeDocument.objects.all(),'corrections':KnowledgeCorrection.objects.select_related('chunk'),'chunks':KnowledgeChunk.objects.all(),'page_title':'课程知识库'})

@login_required
def source(request,chunk_id):
    chunk=get_object_or_404(KnowledgeChunk.objects.select_related('document'),chunk_id=chunk_id)
    page=KnowledgeChunk.objects.filter(document=chunk.document,page_number=chunk.page_number)
    return render(request,'knowledge/source.html',{'chunk':chunk,'page_chunks':page,'corrections':chunk.corrections.all(),'page_title':'原文来源'})

@api_endpoint()
def search(request):
    q=request.GET.get('q','')
    citations=retrieve_knowledge(q)
    return {'query':q,'citations':citations_json(citations),'results':citations_json(citations),'evidence_sufficient':bool(citations),'embedding_provider':__import__('django.conf',fromlist=['settings']).settings.EMBEDDING_PROVIDER}

@api_endpoint()
def points_api(request):
    return {'points':list(KnowledgePoint.objects.values('slug','name','chapter','description','source_page','is_extension'))}
