from django.contrib import admin
from django.db.models import Count
from unfold.admin import ModelAdmin, TabularInline
from django.utils.html import format_html
from django.utils import timezone

from .models import (
    Video,
    Image,
    Detection,
    Tag,
    ImageTag,
    VideoTag,
    DetectionTag,
    Media,
)


class VideoTagInline(TabularInline):
    model = VideoTag
    extra = 1
    autocomplete_fields = ("tag", "tagged_by")

class ImageTagInline(TabularInline):
    model = ImageTag
    extra = 1
    autocomplete_fields = ("tag", "tagged_by")

class DetectionTagInline(TabularInline):
    model = DetectionTag
    extra = 1
    autocomplete_fields = ("tag", "tagged_by")



@admin.register(Media)
class MediaAdmin(ModelAdmin):
    save_on_top = True
    list_per_page = 50

    autocomplete_fields = ("tenant", "created_by", "updated_by")

    list_display = (
        "filename",
        "tenant",
        "media_type_badge",
        "storage_backend",
        "file_size_display",
        "status_badge",
        "is_deleted",
        "created_at",
        "download_link",
    )

    list_filter = (
        "tenant",
        "media_type",
        "storage_backend",
        "status",
        "is_deleted",
        "created_at",
    )

    search_fields = (
        "filename",
        "storage_key",
        "checksum",
        "tenant__name",
    )

    ordering = ("-created_at",)

    readonly_fields = (
        "id",
        "media_id",
        "file_size_display",
        "download_link",
        "created_at",
        "updated_at",
        "deleted_at",
    )

    fieldsets = (
        ("Identity", {
            "fields": (
                "tenant",
                "media_type",
                "filename",
                "file_format",
                "content_type",
            )
        }),
        ("Storage", {
            "fields": (
                "storage_backend",
                "storage_key",
                "file_size_bytes",
                "file_size_display",
            )
        }),
        ("Integrity", {
            "fields": ("checksum",)
        }),
        ("Status", {
            "fields": (
                "status",
                "is_deleted",
                "deleted_at",
            )
        }),
        ("Metadata", {
            "fields": (
                "id",
                "media_id",
                "created_by",
                "updated_by",
                "created_at",
                "updated_at",
            )
        }),
        ("Actions", {
            "fields": ("download_link",)
        }),
    )

    # ─────────────────────────────────────────────
    # Display helpers
    # ─────────────────────────────────────────────

    @admin.display(description="Type")
    def media_type_badge(self, obj):
        colors = {
            "video": "#6366F1",
            "image": "#10B981",
            "detection": "#F59E0B",
        }
        color = colors.get(obj.media_type, "#64748B")

        return format_html(
            '<span style="padding:4px 10px;border-radius:999px;'
            'background:{};color:white;font-size:12px;">{}</span>',
            color,
            obj.get_media_type_display(),
        )

    @admin.display(description="Size")
    def file_size_display(self, obj):
        return f"{obj.file_size_mb:.2f} MB"

    @admin.display(description="Status")
    def status_badge(self, obj):
        colors = {
            "uploaded": "#64748B",
            "processing": "#F59E0B",
            "completed": "#10B981",
            "failed": "#EF4444",
        }

        color = colors.get(obj.status, "#64748B")

        return format_html(
            '<span style="padding:4px 10px;border-radius:999px;'
            'background:{};color:white;font-size:12px;">{}</span>',
            color,
            obj.get_status_display(),
        )

    @admin.display(description="Download")
    def download_link(self, obj):
        try:
            url = obj.get_download_url()
            return format_html(
                '<a href="{}" target="_blank" '
                'style="padding:4px 10px;background:#3B82F6;color:white;'
                'border-radius:6px;text-decoration:none;">Download</a>',
                url,
            )
        except Exception:
            return "—"

    # ─────────────────────────────────────────────
    # Admin actions
    # ─────────────────────────────────────────────

    actions = (
        "soft_delete_media",
        "restore_media",
    )

    @admin.action(description="Soft delete selected media")
    def soft_delete_media(self, request, queryset):
        updated = 0
        for media in queryset:
            if not media.is_deleted:
                media.soft_delete()
                updated += 1
        self.message_user(request, f"{updated} media items soft deleted.")

    @admin.action(description="Restore soft-deleted media")
    def restore_media(self, request, queryset):
        updated = queryset.update(is_deleted=False, deleted_at=None)
        self.message_user(request, f"{updated} media items restored.")


# ----------------------------------
# Video Admin
# ----------------------------------
@admin.register(Video)
class VideoAdmin(ModelAdmin):
    save_on_top = True
    list_per_page = 50

    autocomplete_fields = ("tenant", "created_by", "updated_by")
    inlines = [VideoTagInline]

    list_display = (
        "filename",
        "tenant",
        "plant_site",
        "status_badge",
        "duration_display",
        "resolution_display",
        "frame_count",
        "file_size_display",
        "storage_backend",
        "recorded_at",
    )

    list_filter = (
        "tenant",
        "status",
        "storage_backend",
        "plant_site",
        "recorded_at",
    )

    search_fields = (
        "filename",
        "plant_site",
        "inspection_line",
        "storage_key",
    )

    readonly_fields = (
        "video_id",
        "created_at",
        "updated_at",
        "frame_count",
        "file_size_display",
        "duration_display",
        "resolution_display",
    )

    ordering = ("-recorded_at",)

    fieldsets = (
        ("Basic Info", {
            "fields": ("tenant", "filename", "status")
        }),
        ("File Info", {
            "fields": (
                "file_size_bytes",
                "file_size_display",
                "duration_seconds",
                "duration_display",
                "storage_backend",
                "storage_key",
            )
        }),
        ("Metadata", {
            "fields": (
                "plant_site",
                "shift",
                "inspection_line",
                "recorded_at",
            )
        }),
        ("Derived Info", {
            "fields": (
                "frame_count",
                "resolution_display",
            )
        }),
        ("Audit", {
            "fields": ("created_by", "updated_by", "created_at", "updated_at")
        }),
    )

    # ---------- QUERYSET ----------

    def get_queryset(self, request):
        from django.db.models import Count
        return (
            super()
            .get_queryset(request)
        )

    # ---------- DISPLAY HELPERS ----------

    @admin.display(description="Status")
    def status_badge(self, obj):
        colors = {
            "uploaded": "#64748B",
            "processing": "#F59E0B",
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

    @admin.display(description="Size")
    def file_size_display(self, obj):
        return f"{obj.file_size_mb:.2f} MB"

    @admin.display(description="Duration")
    def duration_display(self, obj):
        if obj.duration_seconds:
            return f"{obj.duration_minutes:.2f} min"
        return "—"

    @admin.display(description="Resolution")
    def resolution_display(self, obj):
        return obj.resolution or "Unknown"
    
# ----------------------------------
# Image Admin
# ----------------------------------
@admin.register(Image)
class ImageAdmin(ModelAdmin):
    save_on_top = True
    list_per_page = 50

    autocomplete_fields = ("tenant", "video", "created_by", "updated_by")
    inlines = [ImageTagInline]

    list_display = (
        "filename",
        "tenant",
        "plant_site",
        "video",
        "resolution",
        "frame_info",
        "status",
        "file_size_display",
        "captured_at",
    )

    list_filter = (
        "tenant",
        "status",
        "plant_site",
        "video",
        "captured_at",
    )

    search_fields = (
        "filename",
        "plant_site",
        "inspection_line",
        "storage_key",
    )

    readonly_fields = (
        "image_id",
        "file_size_display",
        "resolution",
        "created_at",
        "updated_at",
    )

    ordering = ("-captured_at",)

    @admin.display(description="Size")
    def file_size_display(self, obj):
        return f"{obj.file_size_mb:.2f} MB"
    
# ----------------------------------
# Detection Admin
# ----------------------------------
@admin.register(Detection)
class DetectionAdmin(ModelAdmin):
    save_on_top = True
    list_per_page = 50

    autocomplete_fields = ("tenant", "image")
    inlines = [DetectionTagInline]

    list_display = (
        "label",
        "tenant",
        "image",
        "confidence_bar",
        "bbox_format",
        "embedding_status",
        "created_at",
    )

    list_filter = (
        "tenant",
        "label",
        "embedding_generated",
        "bbox_format",
        "created_at",
    )

    search_fields = (
        "label",
        "image__filename",
        "vector_point_id",
    )

    readonly_fields = (
        "detection_id",
        "absolute_bbox_display",
        "normalized_bbox_display",
        "created_at",
        "updated_at",
    )

    ordering = ("-created_at",)

    # ---------- DISPLAY ----------

    @admin.display(description="Confidence")
    def confidence_bar(self, obj):
        percent = int(obj.confidence * 100)
        color = "#10B981" if percent > 80 else "#F59E0B" if percent > 50 else "#EF4444"

        return format_html(
            """
            <div style="width:120px;">
                <div style="background:#E5E7EB;border-radius:6px;height:8px;">
                    <div style="width:{}%;background:{};height:8px;border-radius:6px;"></div>
                </div>
                <small>{}%</small>
            </div>
            """,
            percent,
            color,
            percent,
        )

    @admin.display(description="Embedding")
    def embedding_status(self, obj):
        if obj.has_embedding:
            return format_html(
                '<span style="color:#10B981;font-weight:600;">✓ Embedded</span>'
            )
        return format_html(
            '<span style="color:#EF4444;">Not Generated</span>'
        )

    @admin.display(description="Absolute BBox")
    def absolute_bbox_display(self, obj):
        try:
            return obj.absolute_bbox
        except Exception:
            return "—"

    @admin.display(description="Normalized BBox")
    def normalized_bbox_display(self, obj):
        try:
            return obj.normalized_bbox
        except Exception:
            return "—"

    actions = ("generate_embeddings", "clear_embeddings")

    @admin.action(description="Generate embeddings (dummy)")
    def generate_embeddings(self, request, queryset):
        for obj in queryset:
            obj.generate_embedding("admin-manual")
        self.message_user(request, "Embeddings generated.")

    @admin.action(description="Clear embeddings")
    def clear_embeddings(self, request, queryset):
        queryset.update(
            vector_point_id=None,
            embedding_generated=False,
            embedding_model_version=None,
        )
        self.message_user(request, "Embeddings cleared.")

# ----------------------------------
# Tag Admins
# ----------------------------------
@admin.register(Tag)
class TagAdmin(ModelAdmin):
    list_display = (
        "name",
        "tenant",
        "color_preview",
        "usage_total",
        "created_at",
    )

    list_filter = ("tenant",)
    search_fields = ("name",)

    @admin.display(description="Color")
    def color_preview(self, obj):
        return format_html(
            '<div style="width:20px;height:20px;border-radius:4px;background:{};"></div>',
            obj.color,
        )

    @admin.display(description="Total Usage")
    def usage_total(self, obj):
        return obj.usage_count["total"]