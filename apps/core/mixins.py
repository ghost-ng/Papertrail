"""Reusable mixins for views and models."""

from django.contrib import messages
from django.shortcuts import redirect

from apps.core.models import AuditLog


class AuditLogMixin:
    """Mixin to add audit logging to views."""

    def log_action(self, action: str, resource_type: str, resource_id: str,
                   organization=None, changes: dict = None, metadata: dict = None):
        """Create an audit log entry."""
        AuditLog.objects.create(
            actor=self.request.user if self.request.user.is_authenticated else None,
            actor_email=getattr(self.request.user, "email", ""),
            ip_address=self.get_client_ip(),
            action=action,
            resource_type=resource_type,
            resource_id=str(resource_id),
            organization=organization,
            changes=changes or {},
            metadata=metadata or {},
        )

    def get_client_ip(self):
        """Get client IP address from request."""
        x_forwarded_for = self.request.META.get("HTTP_X_FORWARDED_FOR")
        if x_forwarded_for:
            return x_forwarded_for.split(",")[0].strip()
        return self.request.META.get("REMOTE_ADDR")


class LoginRequiredMixin:
    """Mixin that requires user to be logged in."""

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            messages.warning(request, "Please log in to access this page.")
            return redirect("accounts:login")
        return super().dispatch(request, *args, **kwargs)
