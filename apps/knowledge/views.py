from django.shortcuts import render,get_object_or_404
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.views.decorators.cache import never_cache
from core.http import api_endpoint
from core.exceptions import KnowledgeRetrievalError, ValidationError
from .models import KnowledgePoint,KnowledgeDocument,KnowledgeChunk,KnowledgeCorrection
from .services.retrieval_service import retrieve_knowledge,citations_json

@login_required
def index(request):
    points=KnowledgePoint.objects.all()
    if request.GET.get('chapter','').isdigit(): points=points.filter(chapter=int(request.GET['chapter']))
    return render(request,'knowledge/index.html',{'points':points,'documents':KnowledgeDocument.objects.all(),'corrections':KnowledgeCorrection.objects.select_related('chunk'),'chunks':KnowledgeChunk.objects.all(),'page_title':'课程知识库'})

def _require_chunk_access(user, chunk):
    """Private workspace documents are unreadable outside their workspace."""
    from django.core.exceptions import PermissionDenied
    from apps.workspace.permissions import can_read
    links = list(chunk.document.workspace_links.select_related('workspace'))
    if not links:
        return
    if any(can_read(user, link.workspace) for link in links):
        return
    raise PermissionDenied


@login_required
def source(request,chunk_id):
    chunk=get_object_or_404(KnowledgeChunk.objects.select_related('document','parent_chunk','media_asset'),chunk_id=chunk_id)
    _require_chunk_access(request.user, chunk)
    page=KnowledgeChunk.objects.filter(document=chunk.document,page_number=chunk.page_number)
    parent=chunk.parent_chunk
    children=chunk.children.filter(is_active=True)[:12]
    siblings=parent.children.filter(is_active=True).exclude(pk=chunk.pk)[:6] if parent else []
    return render(request,'knowledge/source.html',{
        'chunk':chunk,'page_chunks':page,'corrections':chunk.corrections.all(),
        'parent':parent,'children':children,'siblings':siblings,
        'claims':chunk.claims.all()[:6],
        'media_assets':chunk.document.media_assets.all()[:6],
        'page_title':'原文来源',
    })

@api_endpoint()
def search(request):
    q=request.GET.get('q','')
    requested_mode=request.GET.get('mode',getattr(settings,'EVIDENCE_RAG_DEFAULT_MODE','legacy')).strip().lower()
    if requested_mode=='advanced':
        from .services.hybrid_retrieval import advanced_retrieve
        result=advanced_retrieve(q,user=request.user)
        payload=result.to_dict()
        payload.update({'query':q,'results':payload['citations'],'citation_check':payload.get('citation_check',{})})
        return payload
    citations=retrieve_knowledge(q)
    return {'query':q,'citations':citations_json(citations),'results':citations_json(citations),'evidence_sufficient':bool(citations),'embedding_provider':settings.EMBEDDING_PROVIDER}

@api_endpoint()
def points_api(request):
    return {'points':list(KnowledgePoint.objects.values('slug','name','chapter','description','source_page','is_extension'))}


@login_required
def local_learning(request):
    from .models import WikipediaCache
    from django.utils import timezone
    articles = list(WikipediaCache.objects.order_by('-retrieved_at')[:12])
    for article in articles:
        article.is_stale = article.expires_at <= timezone.now()
    return render(request, 'knowledge/local.html', {
        'points': KnowledgePoint.objects.all(),
        'cached_articles': articles,
        'page_title': '本地学习',
    })


@login_required
def wikipedia_page(request):
    return render(request, 'knowledge/wikipedia.html', {'page_title': 'Wikipedia 百科查询', 'default_language': settings.WIKIPEDIA_DEFAULT_LANGUAGE})


def _query(request):
    query = request.GET.get('q', '').strip()
    if not query or len(query) > 1000:
        raise ValidationError('请输入 1 至 1000 字的检索词。')
    return query


@never_cache
@api_endpoint()
def wikipedia_search(request):
    from .services.wikipedia_service import search_wikipedia
    query = _query(request)
    language = request.GET.get('language', settings.WIKIPEDIA_DEFAULT_LANGUAGE)
    if language not in ('zh', 'en'):
        raise ValidationError('目前支持中文和英文维基百科。')
    return {'query': query, 'result': search_wikipedia(query, language=language,
        force_refresh=request.GET.get('refresh') == '1', cache_only=request.GET.get('cache_only') == '1')}


@never_cache
@api_endpoint()
def local_search(request):
    """Retrieve local evidence and an optional historical encyclopedia cache; no LLM or HTTP."""
    from .services.wikipedia_service import search_wikipedia
    query = _query(request)
    language = request.GET.get('language', settings.WIKIPEDIA_DEFAULT_LANGUAGE)
    if language not in ('zh', 'en'):
        raise ValidationError('目前支持中文和英文维基百科。')
    retrieval_error = None
    try:
        citations = citations_json(retrieve_knowledge(query))
    except KnowledgeRetrievalError as exc:
        citations, retrieval_error = [], exc.message
    try:
        cached = search_wikipedia(query, language=language, cache_only=True)
    except ValidationError as exc:
        # A long/private course question may still have local RAG evidence. The
        # encyclopedia cache accepts public concepts only, so retain course hits.
        cached = {'success': False, 'from_cache': False, 'source_type': 'wikipedia',
                  'cache_status': 'MISS', 'error': exc.message, 'error_code': exc.code}
    return {'query': query, 'mode': 'LOCAL_RETRIEVAL', 'citations': citations, 'wikipedia': cached,
        'retrieval_error': retrieval_error, 'generated_by_ai': False,
        'message': '当前使用本地知识检索模式。以下内容是课程证据与历史百科缓存，没有调用大模型生成解释。'}
