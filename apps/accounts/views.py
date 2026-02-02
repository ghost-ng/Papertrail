"""Views for accounts app."""

from django.contrib.auth import login
from django.contrib.auth.views import LoginView, LogoutView
from django.urls import reverse_lazy
from django.views.generic import CreateView

from apps.core.mixins import AuditLogMixin

from .forms import CustomUserCreationForm, CustomAuthenticationForm


class RegisterView(AuditLogMixin, CreateView):
    """User registration view."""

    form_class = CustomUserCreationForm
    template_name = "accounts/register.html"
    success_url = reverse_lazy("core:dashboard")

    def form_valid(self, form):
        response = super().form_valid(form)
        login(self.request, self.object)
        self.log_action(
            action="registered",
            resource_type="User",
            resource_id=self.object.id,
        )
        return response


class CustomLoginView(AuditLogMixin, LoginView):
    """Custom login view."""

    form_class = CustomAuthenticationForm
    template_name = "accounts/login.html"

    def form_valid(self, form):
        response = super().form_valid(form)
        self.log_action(
            action="logged_in",
            resource_type="User",
            resource_id=self.request.user.id,
        )
        return response


class CustomLogoutView(AuditLogMixin, LogoutView):
    """Custom logout view."""

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            self.log_action(
                action="logged_out",
                resource_type="User",
                resource_id=request.user.id,
            )
        return super().dispatch(request, *args, **kwargs)
