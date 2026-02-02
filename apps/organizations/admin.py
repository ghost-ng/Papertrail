"""Admin configuration for organizations app."""

from django.contrib import admin

from .models import Organization, Office, OrganizationMembership, OfficeMembership


class OfficeInline(admin.TabularInline):
    """Inline admin for offices."""

    model = Office
    extra = 0
    fields = ("code", "name", "parent", "is_active")


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    """Admin configuration for Organization model."""

    list_display = ("code", "name", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("code", "name")
    inlines = [OfficeInline]


@admin.register(Office)
class OfficeAdmin(admin.ModelAdmin):
    """Admin configuration for Office model."""

    list_display = ("__str__", "name", "organization", "parent", "is_active")
    list_filter = ("is_active", "organization")
    search_fields = ("code", "name", "organization__code")
    raw_id_fields = ("parent",)


@admin.register(OrganizationMembership)
class OrganizationMembershipAdmin(admin.ModelAdmin):
    """Admin configuration for OrganizationMembership model."""

    list_display = ("user", "organization", "role", "status", "requested_at")
    list_filter = ("status", "role", "organization")
    search_fields = ("user__email", "organization__code")
    raw_id_fields = ("user", "reviewed_by")


@admin.register(OfficeMembership)
class OfficeMembershipAdmin(admin.ModelAdmin):
    """Admin configuration for OfficeMembership model."""

    list_display = ("user", "office", "role", "joined_at")
    list_filter = ("role", "office__organization")
    search_fields = ("user__email", "office__code", "office__organization__code")
    raw_id_fields = ("user", "added_by")
