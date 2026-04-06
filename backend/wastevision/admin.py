from django.contrib import admin
from unfold.admin import ModelAdmin
from .models import WasteCamera, WasteInspection, WasteAlert


@admin.register(WasteCamera)
class WasteCameraAdmin(ModelAdmin):
    list_display = ['name', 'location', 'plant_site', 'stream_type', 'status', 'is_active', 'last_frame_at', 'tenant']
    list_filter = ['stream_type', 'status', 'is_active', 'tenant']
    search_fields = ['name', 'location', 'plant_site']
    readonly_fields = ['camera_uuid', 'last_frame_at', 'consecutive_high', 'created_at', 'updated_at']


@admin.register(WasteInspection)
class WasteInspectionAdmin(ModelAdmin):
    list_display = ['inspection_uuid', 'camera', 'overall_risk', 'confidence', 'line_blockage', 'vlm_provider', 'created_at']
    list_filter = ['overall_risk', 'line_blockage', 'vlm_provider', 'tenant']
    search_fields = ['inspector_note', 'camera__name']
    readonly_fields = ['inspection_uuid', 'created_at']


@admin.register(WasteAlert)
class WasteAlertAdmin(ModelAdmin):
    list_display = ['alert_uuid', 'camera', 'alert_type', 'severity', 'is_acknowledged', 'created_at']
    list_filter = ['alert_type', 'severity', 'is_acknowledged', 'tenant']
    search_fields = ['camera__name']
    readonly_fields = ['alert_uuid', 'created_at']
