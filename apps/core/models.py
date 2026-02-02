"""Core models - base classes and shared models."""

import uuid

from django.db import models
from django.utils import timezone


class TimeStampedModel(models.Model):
    """Abstract base model with created/updated timestamps."""

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class AuditLog(models.Model):
    """Immutable audit log for tracking all system actions."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    timestamp = models.DateTimeField(default=timezone.now, db_index=True)

    # Actor information (captured at time of action)
    actor = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs",
    )
    actor_email = models.EmailField(blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    # Action details
    action = models.CharField(max_length=50)  # created, updated, deleted, signed, etc.
    resource_type = models.CharField(max_length=100)  # Package, Document, etc.
    resource_id = models.CharField(max_length=100)

    # Organization scope (for filtering)
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs",
    )

    # Change details
    changes = models.JSONField(default=dict, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-timestamp"]
        indexes = [
            models.Index(fields=["timestamp"]),
            models.Index(fields=["organization", "timestamp"]),
            models.Index(fields=["resource_type", "resource_id"]),
            models.Index(fields=["actor"]),
        ]

    def __str__(self):
        return f"{self.action} {self.resource_type}:{self.resource_id} at {self.timestamp}"

    def save(self, *args, **kwargs):
        """Prevent updates to audit log entries."""
        if self.pk and AuditLog.objects.filter(pk=self.pk).exists():
            raise ValueError("AuditLog entries cannot be modified after creation.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        """Prevent deletion of audit log entries."""
        raise ValueError("AuditLog entries cannot be deleted.")


class SystemSetting(TimeStampedModel):
    """System-wide configuration settings manageable via admin UI."""

    key = models.CharField(max_length=100, unique=True)
    value = models.JSONField()
    description = models.TextField(blank=True)
    category = models.CharField(max_length=50, default="general")
    updated_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="updated_settings",
    )

    class Meta:
        ordering = ["category", "key"]

    def __str__(self):
        return f"{self.key}: {self.value}"

    @classmethod
    def get_value(cls, key: str, default=None):
        """Get a setting value by key."""
        try:
            return cls.objects.get(key=key).value
        except cls.DoesNotExist:
            return default

    @classmethod
    def set_value(cls, key: str, value, user=None, description: str = "", category: str = "general"):
        """Set a setting value by key."""
        setting, _ = cls.objects.update_or_create(
            key=key,
            defaults={
                "value": value,
                "description": description,
                "category": category,
                "updated_by": user,
            },
        )
        return setting
