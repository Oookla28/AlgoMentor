from django.contrib import admin
from .models import KnowledgePoint,KnowledgeDocument,KnowledgeChunk,KnowledgeCorrection,KnowledgeRelation,Course,Chapter
admin.site.register([KnowledgePoint,KnowledgeDocument,KnowledgeChunk,KnowledgeRelation,Course,Chapter])

@admin.register(KnowledgeCorrection)
class CorrectionAdmin(admin.ModelAdmin):
    list_display=['id','status','reviewed_by','created_at']
    readonly_fields=['reviewed_by','created_at']
    def save_model(self,request,obj,form,change):
        if obj.status in ('APPROVED','REJECTED'): obj.reviewed_by=request.user
        else: obj.reviewed_by=None
        super().save_model(request,obj,form,change)
