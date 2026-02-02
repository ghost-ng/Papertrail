"""Core middleware including audit logging."""

import threading

from django.utils.deprecation import MiddlewareMixin

# Thread-local storage for request context
_request_context = threading.local()


def get_current_request():
    """Get the current request from thread-local storage."""
    return getattr(_request_context, "request", None)


def get_current_user():
    """Get the current user from the request."""
    request = get_current_request()
    if request and hasattr(request, "user") and request.user.is_authenticated:
        return request.user
    return None


def get_client_ip():
    """Get the client IP from the current request."""
    request = get_current_request()
    if not request:
        return None

    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


class RequestContextMiddleware(MiddlewareMixin):
    """Store request in thread-local for access by models/services."""

    def process_request(self, request):
        _request_context.request = request

    def process_response(self, request, response):
        if hasattr(_request_context, "request"):
            del _request_context.request
        return response

    def process_exception(self, request, exception):
        if hasattr(_request_context, "request"):
            del _request_context.request


class AuditMiddleware(MiddlewareMixin):
    """Middleware to automatically capture audit context."""

    def process_request(self, request):
        # Store audit context that can be used by services
        request.audit_context = {
            "ip_address": self._get_client_ip(request),
            "user_agent": request.META.get("HTTP_USER_AGENT", ""),
        }

    def _get_client_ip(self, request):
        x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
        if x_forwarded_for:
            return x_forwarded_for.split(",")[0].strip()
        return request.META.get("REMOTE_ADDR")
