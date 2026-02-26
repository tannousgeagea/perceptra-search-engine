from django.contrib import admin
from django.utils.html import format_html
from django.utils import timezone
from django.db.models import F
from unfold.admin import ModelAdmin

from .models import ModelVersion, EmbeddingJob

@admin.register(ModelVersion)
class ModelVersionAdmin(ModelAdmin):
    save_on_top = True
    list_per_page = 25

    list_display = (
        "name",
        "version",
        "vector_dimension",
        "is_active",
        "created_at",
    )

    list_filter = ("is_active", "created_at")
    search_fields = ("name", "version")

    readonly_fields = ("model_version_id", "created_at")

    ordering = ("-created_at",)

    fieldsets = (
        ("Model Info", {
            "fields": (
                "name",
                "version",
                "vector_dimension",
                "is_active",
            )
        }),
        ("Metadata", {
            "fields": (
                "model_version_id",
                "created_at",
            )
        }),
    )

    actions = ["activate_models", "deactivate_models"]

    @admin.action(description="Activate selected models")
    def activate_models(self, request, queryset):
        queryset.update(is_active=True)
        self.message_user(request, "Selected models activated.")

    @admin.action(description="Deactivate selected models")
    def deactivate_models(self, request, queryset):
        queryset.update(is_active=False)
        self.message_user(request, "Selected models deactivated.")

@admin.register(EmbeddingJob)
class EmbeddingJobAdmin(ModelAdmin):
    save_on_top = True
    list_per_page = 50

    autocomplete_fields = ("tenant", "model_version", "created_by", "updated_by")

    list_display = (
        "embedding_job_id",
        "tenant",
        "model_version",
        "status_badge",
        "progress_bar",
        "total_detections",
        "execution_time_display",
        "created_at",
    )

    list_filter = (
        "tenant",
        "status",
        "model_version",
        "created_at",
    )

    search_fields = (
        "embedding_job_id",
        "tenant__name",
        "model_version__name",
    )

    ordering = ("-created_at",)

    readonly_fields = (
        "embedding_job_id",
        "progress_bar",
        "execution_time_display",
        "created_at",
        "updated_at",
    )

    fieldsets = (
        ("Job Info", {
            "fields": (
                "tenant",
                "model_version",
                "status",
            )
        }),
        ("Progress", {
            "fields": (
                "total_detections",
                "processed_detections",
                "failed_detections",
                "progress_bar",
            )
        }),
        ("Timing", {
            "fields": (
                "started_at",
                "completed_at",
                "execution_time_display",
            )
        }),
        ("Errors", {
            "fields": ("error_message",),
        }),
        ("Audit", {
            "fields": (
                "embedding_job_id",
                "created_by",
                "updated_by",
                "created_at",
                "updated_at",
            )
        }),
    )

    # ─────────────────────────────
    # DISPLAY HELPERS
    # ─────────────────────────────

    @admin.display(description="Status")
    def status_badge(self, obj):
        colors = {
            "pending": "#64748B",
            "running": "#F59E0B",
            "completed": "#10B981",
            "failed": "#EF4444",
        }
        color = colors.get(obj.status, "#6B7280")

        return format_html(
            '<span style="padding:4px 10px;border-radius:999px;'
            'background:{};color:white;font-size:12px;">{}</span>',
            color,
            obj.get_status_display(),
        )

    @admin.display(description="Progress")
    def progress_bar(self, obj):
        if obj.total_detections == 0:
            return "0%"

        percent = int((obj.processed_detections / obj.total_detections) * 100)

        return format_html(
            """
            <div style="width:150px;">
                <div style="background:#E5E7EB;border-radius:6px;height:8px;">
                    <div style="width:{}%;background:#3B82F6;height:8px;border-radius:6px;"></div>
                </div>
                <small>{}%</small>
            </div>
            """,
            percent,
            percent,
        )

    @admin.display(description="Execution Time")
    def execution_time_display(self, obj):
        if obj.started_at and obj.completed_at:
            delta = obj.completed_at - obj.started_at
            return f"{int(delta.total_seconds())} sec"
        return "—"