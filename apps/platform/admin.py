from django.contrib import admin

from .models import (
    AgentRun, AgentStep, Claim, ConflictSet, DomainPack, EvaluationCase,
    EvaluationRun, Evidence, TaskPack, ToolSpecRecord,
)

admin.site.register([DomainPack, TaskPack, ToolSpecRecord, AgentRun, AgentStep, Evidence, Claim, ConflictSet, EvaluationCase, EvaluationRun])
