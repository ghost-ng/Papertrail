"""Admin configuration for accounts app."""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """Admin configuration for User model."""

    list_display = ("email", "first_name", "last_name", "auth_method", "is_active", "is_staff")
    list_filter = ("is_active", "is_staff", "auth_method", "pki_status")
    search_fields = ("email", "first_name", "last_name")
    ordering = ("email",)

    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Personal info", {"fields": ("first_name", "last_name")}),
        ("Authentication", {"fields": ("auth_method",)}),
        (
            "PKI",
            {
                "fields": (
                    "pki_status",
                    "pki_certificate_fingerprint",
                    "pki_approved_at",
                    "pki_approved_by",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            "PGP",
            {
                "fields": ("pgp_key_fingerprint", "pgp_key_created_at"),
                "classes": ("collapse",),
            },
        ),
        (
            "Permissions",
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                ),
            },
        ),
        ("Important dates", {"fields": ("last_login", "date_joined")}),
    )

    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "email",
                    "first_name",
                    "last_name",
                    "password1",
                    "password2",
                    "auth_method",
                ),
            },
        ),
    )
