# apps/tenants/admin.py

from django.db import models
from django.contrib import admin
from unfold.admin import ModelAdmin, TabularInline
from django.db.models import Count
from django.utils.html import format_html
from django.utils import timezone

from .models import Tenant, TenantMembership


# ---------- Inlines ----------

class TenantMembershipInline(TabularInline):
    model = TenantMembership
    extra = 0
    autocomplete_fields = ("user",)
    fields = ("user", "role", "is_active", "created_at")
    readonly_fields = ("created_at",)
    show_change_link = True

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related("user")


# ---------- Filters ----------

class ActiveStatusFilter(admin.SimpleListFilter):
    title = "status"
    parameter_name = "status"

    def lookups(self, request, model_admin):
        return (
            ("active", "Active"),
            ("inactive", "Inactive"),
        )

    def queryset(self, request, queryset):
        if self.value() == "active":
            return queryset.filter(is_active=True)
        if self.value() == "inactive":
            return queryset.filter(is_active=False)
        return queryset


# ---------- Tenant Admin ----------

@admin.register(Tenant)
class TenantAdmin(ModelAdmin):
    save_on_top = True
    list_per_page = 50

    inlines = (TenantMembershipInline,)

    # Make slug easier to manage
    prepopulated_fields = {"slug": ("name",)}

    # Best-practice list view
    list_display = (
        "name",
        "slug",
        "domain_badge",
        "location",
        "timezone",
        "storage_quota",
        "api_quota",
        "members_active_count",
        "is_active",
        "updated_at",
    )
    list_editable = ("is_active",)
    list_filter = (ActiveStatusFilter, "timezone", "location")
    search_fields = ("name", "slug", "domain", "location", "vector_collection_name")
    ordering = ("name",)

    readonly_fields = ("tenant_id", "created_at", "updated_at", "vector_collection_name_preview")

    fieldsets = (
        ("Basics", {
            "fields": ("name", "slug", "is_active"),
            "description": "Core tenant identity and status.",
        }),
        ("Routing", {
            "fields": ("domain", "location", "timezone"),
            "description": "Used for tenant routing and display context.",
        }),
        ("Limits & Quotas", {
            "fields": ("max_storage_gb", "max_api_calls_per_day"),
        }),
        ("Vector Database", {
            "fields": ("vector_collection_name", "vector_collection_name_preview"),
            "description": "Collection name used in Qdrant/Vector DB indexing.",
        }),
        ("Metadata", {
            "fields": ("tenant_id", "created_at", "updated_at"),
        }),
    )

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.annotate(
            _active_members=Count("memberships", filter=models.Q(memberships__is_active=True), distinct=True),
        )

    @admin.display(description="Domain")
    def domain_badge(self, obj: Tenant):
        # Small visual polish (badge look)
        return format_html(
            '<span style="display:inline-block;padding:2px 8px;border-radius:999px;'
            'border:1px solid #d1d5db;background:#f9fafb;font-family:ui-monospace, SFMono-Regular, Menlo, monospace;'
            'font-size:12px;">{}</span>',
            obj.domain or "—",
        )

    @admin.display(description="Storage", ordering="max_storage_gb")
    def storage_quota(self, obj: Tenant):
        return f"{obj.max_storage_gb} GB"

    @admin.display(description="API/day", ordering="max_api_calls_per_day")
    def api_quota(self, obj: Tenant):
        return f"{obj.max_api_calls_per_day:,}"

    @admin.display(description="Active members")
    def members_active_count(self, obj: Tenant):
        # Uses annotated value (fast)
        val = getattr(obj, "_active_members", 0)
        return val

    @admin.display(description="Vector collection")
    def vector_collection_name_preview(self, obj: Tenant):
        if not obj.vector_collection_name:
            return "—"
        return format_html(
            '<code style="font-size:12px;padding:2px 6px;border-radius:6px;background:#111827;color:#f9fafb;">{}</code>',
            obj.vector_collection_name,
        )

    actions = ("activate_tenants", "deactivate_tenants")

    @admin.action(description="Activate selected tenants")
    def activate_tenants(self, request, queryset):
        updated = queryset.update(is_active=True, updated_at=timezone.now())
        self.message_user(request, f"Activated {updated} tenant(s).")

    @admin.action(description="Deactivate selected tenants")
    def deactivate_tenants(self, request, queryset):
        updated = queryset.update(is_active=False, updated_at=timezone.now())
        self.message_user(request, f"Deactivated {updated} tenant(s).")


# ---------- TenantMembership Admin ----------

@admin.register(TenantMembership)
class TenantMembershipAdmin(ModelAdmin):
    save_on_top = True
    list_per_page = 50

    autocomplete_fields = ("user", "tenant")

    list_display = (
        "user_email",
        "tenant",
        "role",
        "is_active",
        "created_at",
        "updated_at",
    )
    list_filter = ("role", "is_active", "tenant")
    search_fields = ("user__email", "user__username", "tenant__name", "tenant__slug", "tenant__domain")
    ordering = ("tenant__name", "user__email")

    readonly_fields = ("tenant_membership_id", "created_at", "updated_at")

    fieldsets = (
        ("Membership", {"fields": ("user", "tenant", "role", "is_active")}),
        ("Metadata", {"fields": ("tenant_membership_id", "created_at", "updated_at")}),
    )

    @admin.display(description="User")
    def user_email(self, obj: TenantMembership):
        # Works even if user model doesn't have email, but you do in __str__
        return getattr(obj.user, "email", None) or str(obj.user)