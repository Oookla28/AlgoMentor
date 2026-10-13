from core.http import api_endpoint
from apps.agents.models import AgentTrace
from apps.agents.services.trace_service import serialize_trace

@api_endpoint()
def traces(request):
    rows=AgentTrace.objects.filter(user=request.user).prefetch_related('invocations')[:30]
    return {'traces':[serialize_trace(row) for row in rows]}

@api_endpoint()
def trace_detail(request,trace_id):
    return serialize_trace(AgentTrace.objects.prefetch_related('invocations').get(pk=trace_id,user=request.user))
