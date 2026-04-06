from django.contrib import admin
from django.db.models import Count
from unfold.admin import ModelAdmin
from django.utils.html import format_html
from django.utils.timezone import now

from .models import (
    ModelVersion,
    TenantVectorCollection,
    EmbeddingJob,
    TenantHazardConfig,
    DetectionJob,
)


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────

def pill(text: str, bg: str, fg: str = "white"):
    return format_html(
        '<span style="padding:4px 10px;border-radius:999px;'
        'background:{};color:{};font-size:12px;white-space:nowrap;">{}</span>',
        bg,
        fg,
        text,
    )


# ─────────────────────────────────────────────────────────────
# ModelVersion
# ─────────────────────────────────────────────────────────────

@admin.register(ModelVersion)
class ModelVersionAdmin(ModelAdmin):
    save_on_top = True
    list_per_page = 25

    list_display = (
        "name",
        "model_type_badge",
        "version",
        "vector_dimension",
        "avg_inference_time_display",
        "active_badge",
        "activated_at",
        "created_at",
    )
    list_filter = ("model_type", "is_active", "created_at", "activated_at")
    search_fields = ("name", "version", "description")
    ordering = ("-activated_at", "-created_at")

    readonly_fields = ("model_version_id", "created_at", "updated_at", "collection_suffix_preview")

    fieldsets = (
        ("Identity", {
            "fields": ("name", "model_type", "version", "description"),
        }),
        ("Vectors", {
            "fields": ("vector_dimension", "config", "avg_inference_time_ms"),
        }),
        ("Lifecycle", {
            "fields": ("is_active", "activated_at", "deactivated_at", "collection_suffix_preview"),
            "description": "Only one model can be active at a time (enforced by model.clean()).",
        }),
        ("Metadata", {
            "fields": ("model_version_id", "created_at", "updated_at"),
        }),
    )

    actions = ("activate_selected", "deactivate_selected")

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        # Useful for quick visibility (optional)
        return qs.annotate(_tenant_collections=Count("tenant_collections", distinct=True))

    @admin.display(description="Type")
    def model_type_badge(self, obj: ModelVersion):
        colors = {
            "clip": "#6366F1",
            "dinov2": "#0EA5E9",
            "perception": "#10B981",
            "sam3": "#F59E0B",
        }
        return pill(obj.get_model_type_display(), colors.get(obj.model_type, "#64748B"))   # type: ignore

    @admin.display(description="Inference")
    def avg_inference_time_display(self, obj: ModelVersion):
        if obj.avg_inference_time_ms is None:
            return "—"
        # keep it readable
        return f"{obj.avg_inference_time_ms:.1f} ms"

    @admin.display(description="Active", boolean=False)
    def active_badge(self, obj: ModelVersion):
        return pill("ACTIVE", "#10B981") if obj.is_active else pill("inactive", "#64748B")

    @admin.display(description="Collection suffix")
    def collection_suffix_preview(self, obj: ModelVersion):
        return format_html(
            '<code style="font-size:12px;padding:2px 6px;border-radius:6px;'
            'background:#111827;color:#F9FAFB;">{}</code>',
            obj.collection_suffix,
        )

    @admin.action(description="Activate selected model (deactivate others)")
    def activate_selected(self, request, queryset):
        # Only allow activating exactly one at a time from admin for clarity
        if queryset.count() != 1:
            self.message_user(request, "Please select exactly ONE model to activate.", level="ERROR")
            return
        model = queryset.first()

        # Deactivate currently active models
        ModelVersion.objects.filter(is_active=True).exclude(pk=model.pk).update(
            is_active=False,
            deactivated_at=now(),
        )

        # Activate chosen model
        model.is_active = True
        model.activated_at = now()
        model.deactivated_at = None
        model.save()

        self.message_user(request, f"Activated model: {model.name}")

    @admin.action(description="Deactivate selected models")
    def deactivate_selected(self, request, queryset):
        updated = queryset.update(is_active=False, deactivated_at=now())
        self.message_user(request, f"Deactivated {updated} model(s).")


# ─────────────────────────────────────────────────────────────
# TenantVectorCollection
# ─────────────────────────────────────────────────────────────

@admin.register(TenantVectorCollection)
class TenantVectorCollectionAdmin(ModelAdmin):
    save_on_top = True
    list_per_page = 50

    autocomplete_fields = ("tenant", "model_version")

    list_display = (
        "collection_name_mono",
        "tenant",
        "model_version",
        "db_type_badge",
        "total_vectors",
        "is_active",
        "is_searchable",
        "updated_at",
    )
    list_editable = ("is_active", "is_searchable")
    list_filter = ("db_type", "is_active", "is_searchable", "tenant", "model_version")
    search_fields = ("collection_name", "tenant__name", "model_version__name")
    ordering = ("tenant__name", "-updated_at")

    readonly_fields = ("tenant_vector_collection_id", "created_at", "updated_at")

    fieldsets = (
        ("Identity", {
            "fields": ("tenant", "model_version", "collection_name", "db_type", "purpose"),
        }),
        ("State", {
            "fields": ("is_active", "is_searchable"),
        }),
        ("Stats", {
            "fields": ("total_vectors",),
        }),
        ("Metadata", {
            "fields": ("tenant_vector_collection_id", "created_at", "updated_at"),
        }),
    )

    @admin.display(description="Collection")
    def collection_name_mono(self, obj: TenantVectorCollection):
        return format_html(
            '<code style="font-size:12px;padding:2px 6px;border-radius:6px;'
            'background:#111827;color:#F9FAFB;">{}</code>',
            obj.collection_name,
        )

    @admin.display(description="DB")
    def db_type_badge(self, obj: TenantVectorCollection):
        colors = {"qdrant": "#10B981", "faiss": "#6366F1"}
        return pill(obj.get_db_type_display(), colors.get(obj.db_type, "#64748B"))   # type: ignore


# ─────────────────────────────────────────────────────────────
# EmbeddingJob
# ─────────────────────────────────────────────────────────────

@admin.register(EmbeddingJob)
class EmbeddingJobAdmin(ModelAdmin):
    save_on_top = True
    list_per_page = 50

    autocomplete_fields = ("tenant", "model_version", "collection")

    list_display = (
        "embedding_job_id_short",
        "tenant",
        "job_type_badge",
        "model_version",
        "status_badge",
        "progress_bar",
        "failed_items",
        "started_at",
        "completed_at",
        "created_at",
    )

    list_filter = (
        "tenant",
        "status",
        "job_type",
        "model_version",
        "created_at",
    )
    search_fields = (
        "embedding_job_id",
        "tenant__name",
        "model_version__name",
        "collection__collection_name",
        "error_message",
    )
    ordering = ("-created_at",)

    readonly_fields = (
        "embedding_job_id",
        "progress_bar",
        "progress_percent_display",
        "created_at",
        "updated_at",
    )

    fieldsets = (
        ("Job", {
            "fields": ("tenant", "job_type", "status", "model_version", "collection"),
        }),
        ("Progress", {
            "fields": ("total_items", "processed_items", "failed_items", "progress_percent_display", "progress_bar"),
        }),
        ("Timing", {
            "fields": ("started_at", "completed_at"),
        }),
        ("Errors", {
            "fields": ("error_message",),
        }),
        ("Metadata", {
            "fields": ("embedding_job_id", "created_at", "updated_at"),
        }),
    )

    actions = ("mark_pending", "mark_running", "mark_cancelled")

    @admin.display(description="Job ID")
    def embedding_job_id_short(self, obj: EmbeddingJob):
        return str(obj.embedding_job_id)[:8]

    @admin.display(description="Type")
    def job_type_badge(self, obj: EmbeddingJob):
        colors = {"images": "#0EA5E9", "detections": "#6366F1", "migration": "#F59E0B"}
        return pill(obj.get_job_type_display(), colors.get(obj.job_type, "#64748B"))   # type: ignore

    @admin.display(description="Status")
    def status_badge(self, obj: EmbeddingJob):
        colors = {
            "pending": "#64748B",
            "running": "#F59E0B",
            "completed": "#10B981",
            "failed": "#EF4444",
            "cancelled": "#334155",
        }
        return pill(obj.get_status_display(), colors.get(obj.status, "#64748B"))   # type: ignore
  
    @admin.display(description="Progress %")
    def progress_percent_display(self, obj: EmbeddingJob):
        return f"{obj.progress_percent:.2f}%"

    @admin.display(description="Progress")
    def progress_bar(self, obj: EmbeddingJob):
        pct = obj.progress_percent
        # Color based on status / error
        if obj.status == "failed":
            bar = "#EF4444"
        elif obj.status == "completed":
            bar = "#10B981"
        elif obj.status == "running":
            bar = "#F59E0B"
        else:
            bar = "#6366F1"

        return format_html(
            """
            <div style="width:170px;">
              <div style="background:#E5E7EB;border-radius:6px;height:8px;">
                <div style="width:{pct}%;background:{bar};height:8px;border-radius:6px;"></div>
              </div>
              <small>{pct:.2f}%</small>
            </div>
            """,
            pct=pct,
            bar=bar,
        )

    @admin.action(description="Mark selected jobs as Pending")
    def mark_pending(self, request, queryset):
        updated = queryset.update(status="pending")
        self.message_user(request, f"Updated {updated} job(s) to Pending.")

    @admin.action(description="Mark selected jobs as Running (set started_at if empty)")
    def mark_running(self, request, queryset):
        updated = 0
        for job in queryset:
            if job.status != "running":
                job.status = "running"
                if not job.started_at:
                    job.started_at = now()
                job.save(update_fields=["status", "started_at", "updated_at"])
                updated += 1
        self.message_user(request, f"Updated {updated} job(s) to Running.")

    @admin.action(description="Cancel selected jobs")
    def mark_cancelled(self, request, queryset):
        updated = queryset.update(status="cancelled")
        self.message_user(request, f"Cancelled {updated} job(s).")


# ─────────────────────────────────────────────────────────────
# TenantHazardConfig
# ─────────────────────────────────────────────────────────────

@admin.register(TenantHazardConfig)
class TenantHazardConfigAdmin(ModelAdmin):
    save_on_top = True
    list_per_page = 50

    list_display = (
        "name",
        "tenant",
        "backend_badge",
        "prompts_preview",
        "confidence_threshold",
        "active_badge",
        "default_badge",
        "updated_at",
    )
    list_filter = ("is_active", "is_default", "detection_backend", "tenant")
    search_fields = ("name", "tenant__name")
    ordering = ("tenant__name", "-updated_at")

    readonly_fields = ("created_at", "updated_at")

    fieldsets = (
        ("Identity", {
            "fields": ("tenant", "name"),
        }),
        ("Detection Settings", {
            "fields": ("prompts", "detection_backend", "confidence_threshold", "config"),
            "description": (
                "Prompts: JSON list of text prompts (hazard class names). "
                "Example: [\"metallic pipe\", \"rust\", \"container\"]"
            ),
        }),
        ("Status", {
            "fields": ("is_active", "is_default"),
        }),
        ("Metadata", {
            "fields": ("created_at", "updated_at"),
        }),
    )

    @admin.display(description="Backend")
    def backend_badge(self, obj: TenantHazardConfig):
        return pill(obj.get_detection_backend_display(), "#F59E0B")   # type: ignore

    @admin.display(description="Prompts")
    def prompts_preview(self, obj: TenantHazardConfig):
        if not obj.prompts:
            return "—"
        preview = ", ".join(obj.prompts[:3])
        if len(obj.prompts) > 3:
            preview += f" (+{len(obj.prompts) - 3} more)"
        return preview

    @admin.display(description="Active")
    def active_badge(self, obj: TenantHazardConfig):
        return pill("ACTIVE", "#10B981") if obj.is_active else pill("inactive", "#64748B")

    @admin.display(description="Default")
    def default_badge(self, obj: TenantHazardConfig):
        return pill("DEFAULT", "#6366F1") if obj.is_default else "—"


# ─────────────────────────────────────────────────────────────
# DetectionJob
# ─────────────────────────────────────────────────────────────

@admin.register(DetectionJob)
class DetectionJobAdmin(ModelAdmin):
    save_on_top = True
    list_per_page = 50

    list_display = (
        "detection_job_id_short",
        "tenant",
        "image_link",
        "hazard_config_name",
        "status_badge",
        "total_detections",
        "inference_time_display",
        "started_at",
        "completed_at",
        "created_at",
    )
    list_filter = ("status", "detection_backend", "tenant", "created_at")
    search_fields = (
        "detection_job_id",
        "tenant__name",
        "image__filename",
        "hazard_config__name",
        "error_message",
    )
    ordering = ("-created_at",)

    readonly_fields = (
        "detection_job_id",
        "created_at",
        "updated_at",
    )

    fieldsets = (
        ("Job", {
            "fields": ("tenant", "image", "hazard_config", "detection_backend", "status"),
        }),
        ("Results", {
            "fields": ("total_detections", "inference_time_ms"),
        }),
        ("Timing", {
            "fields": ("started_at", "completed_at"),
        }),
        ("Errors", {
            "fields": ("error_message",),
        }),
        ("Metadata", {
            "fields": ("detection_job_id", "created_at", "updated_at"),
        }),
    )

    @admin.display(description="Job ID")
    def detection_job_id_short(self, obj: DetectionJob):
        return str(obj.detection_job_id)[:8]

    @admin.display(description="Image")
    def image_link(self, obj: DetectionJob):
        return obj.image.filename if obj.image else "—"

    @admin.display(description="Config")
    def hazard_config_name(self, obj: DetectionJob):
        return obj.hazard_config.name if obj.hazard_config else "—"

    @admin.display(description="Status")
    def status_badge(self, obj: DetectionJob):
        colors = {
            "pending": "#64748B",
            "running": "#F59E0B",
            "completed": "#10B981",
            "failed": "#EF4444",
            "skipped": "#334155",
        }
        return pill(obj.get_status_display(), colors.get(obj.status, "#64748B"))   # type: ignore

    @admin.display(description="Inference")
    def inference_time_display(self, obj: DetectionJob):
        if obj.inference_time_ms is None:
            return "—"
        return f"{obj.inference_time_ms:.1f} ms"