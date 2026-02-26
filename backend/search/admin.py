from django.contrib import admin
from django.utils.html import format_html
from django.db.models import Avg, Count
from django.utils.timezone import localtime
from unfold.admin import ModelAdmin

from .models import SearchQuery

@admin.register(SearchQuery)
class SearchQueryAdmin(ModelAdmin):
    save_on_top = True
    list_per_page = 50

    autocomplete_fields = ("tenant", "user")

    list_display = (
        "query_preview",
        "tenant",
        "user",
        "query_type_badge",
        "results_count",
        "execution_time_badge",
        "created_at",
    )

    list_filter = (
        "tenant",
        "query_type",
        "created_at",
        "user",
    )

    search_fields = (
        "query_text",
        "query_image_path",
        "user__email",
    )

    ordering = ("-created_at",)

    readonly_fields = (
        "id",
        "query_type",
        "query_text",
        "query_image_path",
        "filters_pretty",
        "results_count",
        "top_result_id",
        "execution_time_ms",
        "created_at",
        "performance_indicator",
    )

    fieldsets = (
        ("Query Info", {
            "fields": (
                "tenant",
                "user",
                "query_type",
                "query_text",
                "query_image_path",
            )
        }),
        ("Filters Applied", {
            "fields": ("filters_pretty",),
        }),
        ("Results", {
            "fields": ("results_count", "top_result_id"),
        }),
        ("Performance", {
            "fields": (
                "execution_time_ms",
                "performance_indicator",
            ),
        }),
        ("Metadata", {
            "fields": ("id", "created_at"),
        }),
    )

    # ─────────────────────────────
    # DISPLAY METHODS
    # ─────────────────────────────

    @admin.display(description="Query")
    def query_preview(self, obj):
        if obj.query_text:
            return obj.query_text[:60]
        if obj.query_image_path:
            return f"Image Query"
        return "—"

    @admin.display(description="Type")
    def query_type_badge(self, obj):
        colors = {
            "image": "#3B82F6",
            "text": "#6366F1",
            "video": "#10B981",
            "hybrid": "#F59E0B",
        }
        color = colors.get(obj.query_type, "#6B7280")
        return format_html(
            '<span style="padding:4px 10px;border-radius:999px;'
            'background:{};color:white;font-size:12px;">{}</span>',
            color,
            obj.get_query_type_display(),
        )

    @admin.display(description="Execution Time")
    def execution_time_badge(self, obj):
        ms = obj.execution_time_ms

        if ms < 200:
            color = "#10B981"
        elif ms < 800:
            color = "#F59E0B"
        else:
            color = "#EF4444"

        return format_html(
            '<span style="padding:4px 8px;border-radius:8px;'
            'background:{};color:white;font-size:12px;">{} ms</span>',
            color,
            ms,
        )

    @admin.display(description="Filters")
    def filters_pretty(self, obj):
        if not obj.filters:
            return "No filters applied"

        formatted = "<br>".join(
            f"<strong>{k}</strong>: {v}"
            for k, v in obj.filters.items()
        )

        return format_html(formatted)

    @admin.display(description="Performance Indicator")
    def performance_indicator(self, obj):
        ms = obj.execution_time_ms

        if ms < 200:
            status = "Excellent"
            color = "#10B981"
        elif ms < 800:
            status = "Moderate"
            color = "#F59E0B"
        else:
            status = "Slow"
            color = "#EF4444"

        return format_html(
            '<span style="color:{};font-weight:600;">{}</span>',
            color,
            status,
        )
    
    actions = ["show_statistics"]

    @admin.action(description="Show statistics summary")
    def show_statistics(self, request, queryset):
        total = queryset.count()
        avg_time = queryset.aggregate(Avg("execution_time_ms"))["execution_time_ms__avg"]
        self.message_user(
            request,
            f"{total} queries selected. Average execution time: {avg_time:.2f} ms"
        )