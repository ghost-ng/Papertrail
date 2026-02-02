"""Admin Dashboard app configuration."""

from django.apps import AppConfig


class AdminDashboardConfig(AppConfig):
    """Configuration for the admin dashboard app."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.admin_dashboard"
    verbose_name = "Admin Dashboard"
