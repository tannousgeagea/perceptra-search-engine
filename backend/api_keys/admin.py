# apps/tenants/admin.py

from django import forms
from django.contrib import admin, messages
from unfold.admin import ModelAdmin, TabularInline
from django.utils.html import format_html
from django.utils.timezone import now

from .models import APIKey, APIKeyUsageLog


# ─────────────────────────────────────────────────────────────
# Existing tenant admin classes stay as they are...
# Add the classes below for API keys.
# ─────────────────────────────────────────────────────────────


# ---------- Forms ----------

class APIKeyAdminForm(forms.ModelForm):
    class Meta:
        model = APIKey
        fields = (
            "tenant",
            "name",
            "permissions",
            "scopes",
            "rate_limit_per_minute",
            "rate_limit_per_hour",
            "is_active",
            "expires_at",
            "allowed_ips",
        )


# ---------- Inlines ----------

class APIKeyUsageLogInline(TabularInline):
    model = APIKeyUsageLog
    extra = 0
    can_delete = False
    show_change_link = True
    fields = (
        "request_time",
        "method",
        "endpoint",
        "status_code_badge",
        "response_time_display",
        "ip_address",
    )
    readonly_fields = (
        "request_time",
        "method",
        "endpoint",
        "status_code_badge",
        "response_time_display",
        "ip_address",
    )

    def has_add_permission(self, request, obj=None):
        return False

    @admin.display(description="Status")
    def status_code_badge(self, obj):
        if 200 <= obj.status_code < 300:
            color = "#10B981"
        elif 300 <= obj.status_code < 400:
            color = "#3B82F6"
        elif 400 <= obj.status_code < 500:
            color = "#F59E0B"
        else:
            color = "#EF4444"

        return format_html(
            '<span style="padding:3px 8px;border-radius:999px;'
            'background:{};color:white;font-size:12px;">{}</span>',
            color,
            obj.status_code,
        )

    @admin.display(description="Response time")
    def response_time_display(self, obj):
        return f"{obj.response_time_ms} ms"


# ---------- Filters ----------

class APIKeyValidityFilter(admin.SimpleListFilter):
    title = "validity"
    parameter_name = "validity"

    def lookups(self, request, model_admin):
        return (
            ("valid", "Valid"),
            ("expired", "Expired"),
            ("inactive", "Inactive"),
        )

    def queryset(self, request, queryset):
        if self.value() == "valid":
            return queryset.filter(is_active=True).exclude(expires_at__lt=now())
        if self.value() == "expired":
            return queryset.filter(expires_at__lt=now())
        if self.value() == "inactive":
            return queryset.filter(is_active=False)
        return queryset


# ---------- API Key Admin ----------

@admin.register(APIKey)
class APIKeyAdmin(ModelAdmin):
    form = APIKeyAdminForm
    save_on_top = True
    list_per_page = 50

    autocomplete_fields = ("tenant", "created_by")
    inlines = (APIKeyUsageLogInline,)

    list_display = (
        "name",
        "tenant",
        "key_prefix_display",
        "permissions_badge",
        "is_active",
        "validity_badge",
        "rate_limit_display",
        "total_requests",
        "last_used_at",
        "created_at",
    )
    list_filter = (
        "tenant",
        "permissions",
        "is_active",
        APIKeyValidityFilter,
        "created_at",
        "expires_at",
    )
    search_fields = (
        "name",
        "tenant__name",
        "tenant__slug",
        "key_prefix",
    )
    ordering = ("-created_at",)

    readonly_fields = (
        "api_key_id",
        "key_prefix",
        "key_hash_masked",
        "created_by",
        "last_used_at",
        "total_requests",
        "validity_badge",
        "created_at",
        "updated_at",
    )

    fieldsets = (
        ("Identity", {
            "fields": ("tenant", "name", "permissions", "is_active"),
        }),
        ("Access Control", {
            "fields": ("scopes", "allowed_ips"),
            "description": "Leave scopes or allowed IPs empty to allow all.",
        }),
        ("Rate Limits", {
            "fields": ("rate_limit_per_minute", "rate_limit_per_hour"),
        }),
        ("Expiry & Usage", {
            "fields": ("expires_at", "last_used_at", "total_requests", "validity_badge"),
        }),
        ("Key Metadata", {
            "fields": ("api_key_id", "key_prefix", "key_hash_masked", "created_by", "created_at", "updated_at", "owned_by"),
        }),
    )

    actions = ("activate_keys", "deactivate_keys")

    def save_model(self, request, obj, form, change):
        if change:
            super().save_model(request, obj, form, change)
            return

        api_key, raw_key = APIKey.create_key(
            tenant=form.cleaned_data["tenant"],
            name=form.cleaned_data["name"],
            permissions=form.cleaned_data["permissions"],
            created_by=request.user,
            expires_at=form.cleaned_data.get("expires_at"),
            scopes=form.cleaned_data.get("scopes", []),
            rate_limit_per_minute=form.cleaned_data.get("rate_limit_per_minute", 60),
            rate_limit_per_hour=form.cleaned_data.get("rate_limit_per_hour", 1000),
            is_active=form.cleaned_data.get("is_active", True),
            allowed_ips=form.cleaned_data.get("allowed_ips", []),
        )

        # Copy generated instance state back onto obj so Django admin continues normally
        obj.pk = api_key.pk
        obj.id = api_key.pk if hasattr(obj, "id") else None
        obj.api_key_id = api_key.api_key_id
        obj.key_prefix = api_key.key_prefix
        obj.key_hash = api_key.key_hash
        obj.created_by = api_key.created_by
        obj.created_at = api_key.created_at
        obj.updated_at = api_key.updated_at

        # one-time display after creation
        self._generated_raw_key = raw_key

    def response_add(self, request, obj, post_url_continue=None):
        response = super().response_add(request, obj, post_url_continue)
        raw_key = getattr(self, "_generated_raw_key", None)
        if raw_key:
            self.message_user(
                request,
                (
                    "API key created successfully. Copy it now — it will not be shown again: "
                    f"{raw_key}"
                ),
                level=messages.WARNING,
            )
            del self._generated_raw_key
        return response

    @admin.display(description="Prefix")
    def key_prefix_display(self, obj):
        return format_html(
            '<code style="font-size:12px;padding:2px 6px;border-radius:6px;'
            'background:#111827;color:#F9FAFB;">{}...</code>',
            obj.key_prefix,
        )

    @admin.display(description="Permission")
    def permissions_badge(self, obj):
        colors = {
            "read": "#3B82F6",
            "write": "#F59E0B",
            "admin": "#EF4444",
        }
        return format_html(
            '<span style="padding:4px 10px;border-radius:999px;'
            'background:{};color:white;font-size:12px;">{}</span>',
            colors.get(obj.permissions, "#64748B"),
            obj.get_permissions_display(),
        )

    @admin.display(description="Rate limits")
    def rate_limit_display(self, obj):
        return f"{obj.rate_limit_per_minute}/min · {obj.rate_limit_per_hour}/hr"

    @admin.display(description="Validity")
    def validity_badge(self, obj):
        if not obj.is_active:
            return format_html(
                '<span style="color:#64748B;font-weight:600;">Inactive</span>'
            )
        if obj.expires_at and obj.expires_at < now():
            return format_html(
                '<span style="color:#EF4444;font-weight:600;">Expired</span>'
            )
        return format_html(
            '<span style="color:#10B981;font-weight:600;">Valid</span>'
        )

    @admin.display(description="Key hash")
    def key_hash_masked(self, obj):
        if not obj.key_hash:
            return "—"
        return f"{obj.key_hash[:12]}••••••••••••••••••••••••••••••••"

    @admin.action(description="Activate selected API keys")
    def activate_keys(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f"Activated {updated} API key(s).")

    @admin.action(description="Deactivate selected API keys")
    def deactivate_keys(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f"Deactivated {updated} API key(s).")


# ---------- API Key Usage Log Admin ----------

@admin.register(APIKeyUsageLog)
class APIKeyUsageLogAdmin(ModelAdmin):
    save_on_top = True
    list_per_page = 100

    autocomplete_fields = ("api_key",)

    list_display = (
        "request_time",
        "api_key",
        "tenant_name",
        "method",
        "endpoint_short",
        "status_code_badge",
        "response_time_display",
        "ip_address",
    )
    list_filter = (
        "method",
        "status_code",
        "request_time",
        "api_key__tenant",
    )
    search_fields = (
        "endpoint",
        "ip_address",
        "user_agent",
        "api_key__name",
        "api_key__key_prefix",
        "api_key__tenant__name",
    )
    ordering = ("-request_time",)

    readonly_fields = (
        "id",
        "api_key",
        "endpoint",
        "method",
        "status_code",
        "ip_address",
        "user_agent",
        "request_time",
        "response_time_ms",
        "error_message",
    )

    fieldsets = (
        ("Request", {
            "fields": ("api_key", "method", "endpoint", "status_code", "request_time"),
        }),
        ("Client", {
            "fields": ("ip_address", "user_agent"),
        }),
        ("Performance", {
            "fields": ("response_time_ms",),
        }),
        ("Errors", {
            "fields": ("error_message",),
        }),
        ("Metadata", {
            "fields": ("id",),
        }),
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    @admin.display(description="Tenant")
    def tenant_name(self, obj):
        return obj.api_key.tenant.name

    @admin.display(description="Endpoint")
    def endpoint_short(self, obj):
        return obj.endpoint if len(obj.endpoint) <= 60 else f"{obj.endpoint[:57]}..."

    @admin.display(description="Status")
    def status_code_badge(self, obj):
        if 200 <= obj.status_code < 300:
            color = "#10B981"
        elif 300 <= obj.status_code < 400:
            color = "#3B82F6"
        elif 400 <= obj.status_code < 500:
            color = "#F59E0B"
        else:
            color = "#EF4444"

        return format_html(
            '<span style="padding:4px 10px;border-radius:999px;'
            'background:{};color:white;font-size:12px;">{}</span>',
            color,
            obj.status_code,
        )

    @admin.display(description="Response")
    def response_time_display(self, obj):
        return f"{obj.response_time_ms} ms"