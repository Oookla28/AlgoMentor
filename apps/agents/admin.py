from django.contrib import admin
from apps.agents.models import AgentTrace,ToolInvocation
admin.site.register(AgentTrace)
admin.site.register(ToolInvocation)
