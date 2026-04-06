from django.contrib import admin
from .models import Alert, AlertRule


@admin.register(AlertRule)
class AlertRuleAdmin(admin.ModelAdmin):
    list_display = ('name', 'tenant', 'label_pattern', 'min_confidence', 'is_active', 'created_at')
    list_filter = ('is_active', 'tenant')
    search_fields = ('name', 'label_pattern')


@admin.register(Alert)
class AlertAdmin(admin.ModelAdmin):
    list_display = ('label', 'severity', 'confidence', 'plant_site', 'is_acknowledged', 'created_at')
    list_filter = ('severity', 'is_acknowledged', 'tenant')
    search_fields = ('label', 'plant_site')
    raw_id_fields = ('detection', 'image', 'alert_rule', 'acknowledged_by')
