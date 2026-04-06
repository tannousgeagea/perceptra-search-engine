from django.contrib import admin
from .models import ChecklistTemplate, ChecklistInstance, ChecklistItemResult


@admin.register(ChecklistTemplate)
class ChecklistTemplateAdmin(admin.ModelAdmin):
    list_display = ('name', 'tenant', 'plant_site', 'is_active', 'created_at')
    list_filter = ('is_active', 'tenant')
    search_fields = ('name', 'plant_site')


@admin.register(ChecklistInstance)
class ChecklistInstanceAdmin(admin.ModelAdmin):
    list_display = ('template', 'date', 'shift', 'operator', 'status', 'created_at')
    list_filter = ('status', 'shift', 'tenant')
    raw_id_fields = ('template', 'operator')


@admin.register(ChecklistItemResult)
class ChecklistItemResultAdmin(admin.ModelAdmin):
    list_display = ('instance', 'item_index', 'status', 'detection_count', 'completed_at')
    list_filter = ('status',)
    raw_id_fields = ('instance', 'image')
