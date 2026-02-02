"""Core views."""

from django.http import JsonResponse
from django.shortcuts import render
from django.views import View
from django.views.generic import TemplateView

from apps.collaboration.models import Notification
from apps.collaboration.services import NotificationService
from apps.core.mixins import LoginRequiredMixin
from apps.organizations.models import OfficeMembership
from apps.packages.models import Package, StageNode


class DashboardView(LoginRequiredMixin, TemplateView):
    """Main dashboard view - redirects to UserDashboardView."""

    template_name = "core/dashboard.html"


class UserDashboardView(LoginRequiredMixin, View):
    """User's personal dashboard showing their workflow overview."""

    def get(self, request):
        user = request.user

        # Get user's office memberships (membership is immediate)
        memberships = OfficeMembership.objects.filter(
            user=user,
        ).select_related("office", "office__organization")

        office_ids = [m.office_id for m in memberships]

        # Packages requiring action - at stages assigned to user's offices
        action_required = []
        if office_ids:
            packages_in_routing = Package.objects.filter(
                status=Package.Status.IN_ROUTING,
            ).exclude(current_node="").select_related(
                "organization", "workflow_template", "originator"
            )

            for package in packages_in_routing:
                try:
                    stage = StageNode.objects.get(
                        template=package.workflow_template,
                        node_id=package.current_node,
                    )
                    if stage.assigned_offices.filter(id__in=office_ids).exists():
                        action_required.append({"package": package, "stage": stage})
                except StageNode.DoesNotExist:
                    pass

        # My packages
        my_packages = Package.objects.filter(
            originator=user
        ).select_related("organization", "workflow_template").order_by("-created_at")[:10]

        # Notifications
        notifications = Notification.objects.filter(
            user=user
        ).select_related("package").order_by("-created_at")[:10]
        unread_count = NotificationService.get_unread_count(user)

        context = {
            "action_required": action_required,
            "action_required_count": len(action_required),
            "my_packages": my_packages,
            "my_packages_count": my_packages.count() if hasattr(my_packages, "count") else len(my_packages),
            "notifications": notifications,
            "unread_count": unread_count,
            "memberships": memberships,
        }

        return render(request, "dashboards/user_dashboard.html", context)


class ToggleDarkModeView(View):
    """Toggle dark mode preference."""

    def post(self, request):
        if request.user.is_authenticated:
            current = request.session.get("dark_mode", False)
            request.session["dark_mode"] = not current
            return JsonResponse({"dark_mode": not current})
        return JsonResponse({"error": "Not authenticated"}, status=401)
