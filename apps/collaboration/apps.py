"""Collaboration app configuration."""

from django.apps import AppConfig


class CollaborationConfig(AppConfig):
    """Configuration for the collaboration app."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.collaboration"
    verbose_name = "Collaboration"
