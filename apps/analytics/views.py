from core.http import api_endpoint

@api_endpoint()
def traces(request):
    from apps.agents.models import AgentTrace
    from apps.agents.services.trace_service import serialize_trace
    rows=AgentTrace.objects.filter(user=request.user).order_by('-started_at')[:50]
    return {'traces':[serialize_trace(row) for row in rows]}
