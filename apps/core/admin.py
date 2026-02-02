"""Admin configuration for core app."""

from django.contrib import admin

from .models import SystemSetting, AuditLog


@admin.register(SystemSetting)
class SystemSettingAdmin(admin.ModelAdmin):
    """Admin for system settings - branding customization."""

    list_display = ("key", "value", "category", "updated_at")
    list_filter = ("category",)
    search_fields = ("key", "description")
    ordering = ("category", "key")

    fieldsets = (
        (None, {"fields": ("key", "value", "description", "category")}),
        ("Metadata", {"fields": ("updated_by", "updated_at"), "classes": ("collapse",)}),
    )
    readonly_fields = ("updated_at",)


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    """Admin for audit logs - read only."""

    list_display = ("timestamp", "actor_email", "action", "resource_type", "resource_id")
    list_filter = ("action", "resource_type", "organization")
    search_fields = ("actor_email", "resource_id")
    ordering = ("-timestamp",)
    readonly_fields = [f.name for f in AuditLog._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
