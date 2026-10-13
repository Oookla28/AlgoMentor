from django.contrib import admin
from apps.accounts.models import UserProfile,UserAPIConfig,APIUsageRecord

@admin.register(UserAPIConfig)
class UserAPIConfigAdmin(admin.ModelAdmin):
    list_display = ['user','default_tier','last_status','updated_at']
    exclude = ['encrypted_api_key','key_hint']
    readonly_fields = ['user','default_tier','reasoning_effort','last_status','last_checked_at','updated_at']
    def has_add_permission(self,request): return False
    def has_change_permission(self,request,obj=None): return False

admin.site.register(UserProfile)
@admin.register(APIUsageRecord)
class UsageAdmin(admin.ModelAdmin):
    list_display = ['user','model','status','input_tokens','output_tokens','created_at']
    def has_add_permission(self,request): return False
    def has_change_permission(self,request,obj=None): return False
