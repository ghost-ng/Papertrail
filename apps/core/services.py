"""Core services including audit logging."""

from typing import Any, Optional

from .middleware import get_client_ip, get_current_request, get_current_user
from .models import AuditLog


class AuditService:
    """Service for creating audit log entries."""

    @classmethod
    def log(
        cls,
        action: str,
        resource_type: str,
        resource_id: str,
        changes: Optional[dict] = None,
        metadata: Optional[dict] = None,
        actor=None,
        organization=None,
    ) -> AuditLog:
        """Create an audit log entry."""
        request = get_current_request()

        # Get actor from param, request, or None
        if actor is None:
            actor = get_current_user()

        # Get IP address
        ip_address = None
        if request:
            ip_address = get_client_ip()

        # Get actor email
        actor_email = ""
        if actor:
            actor_email = actor.email

        entry = AuditLog.objects.create(
            actor=actor,
            actor_email=actor_email,
            ip_address=ip_address,
            action=action,
            resource_type=resource_type,
            resource_id=str(resource_id),
            organization=organization,
            changes=changes or {},
            metadata=metadata or {},
        )

        return entry

    @classmethod
    def log_create(cls, instance, organization=None):
        """Log a model creation."""
        return cls.log(
            action="created",
            resource_type=instance.__class__.__name__,
            resource_id=instance.pk,
            organization=organization,
            metadata={"model": f"{instance._meta.app_label}.{instance._meta.model_name}"},
        )

    @classmethod
    def log_update(cls, instance, changes: dict, organization=None):
        """Log a model update with changes."""
        return cls.log(
            action="updated",
            resource_type=instance.__class__.__name__,
            resource_id=instance.pk,
            changes=changes,
            organization=organization,
        )

    @classmethod
    def log_delete(cls, instance, organization=None):
        """Log a model deletion."""
        return cls.log(
            action="deleted",
            resource_type=instance.__class__.__name__,
            resource_id=instance.pk,
            organization=organization,
            metadata={"repr": str(instance)},
        )
