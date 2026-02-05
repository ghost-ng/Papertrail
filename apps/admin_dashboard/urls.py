"""URL configuration for admin dashboard app."""

from django.urls import path

from .views import (
    AdminDashboardView,
    AuditLogView,
    OfficeDetailView,
    OfficeManagementView,
    OrganizationDetailView,
    OrganizationManagementView,
    PendingApprovalsView,
    PermissionHierarchyView,
    SystemSettingsView,
    UserDetailView,
    UserManagementView,
    UserSearchAPIView,
    WorkflowManagementView,
)

app_name = "admin_dashboard"

urlpatterns = [
    path("", AdminDashboardView.as_view(), name="index"),
    # User management
    path("users/", UserManagementView.as_view(), name="users"),
    path("users/<int:pk>/", UserDetailView.as_view(), name="user_detail"),
    path("api/users/search/", UserSearchAPIView.as_view(), name="user_search_api"),
    # Organization management
    path("organizations/", OrganizationManagementView.as_view(), name="organizations"),
    path("organizations/<int:pk>/", OrganizationDetailView.as_view(), name="organization_detail"),
    # Office management
    path("offices/", OfficeManagementView.as_view(), name="offices"),
    path("offices/<int:pk>/", OfficeDetailView.as_view(), name="office_detail"),
    # Workflow management
    path("workflows/", WorkflowManagementView.as_view(), name="workflows"),
    # Audit and settings
    path("audit/", AuditLogView.as_view(), name="audit_log"),
    path("settings/", SystemSettingsView.as_view(), name="settings"),
    # Permission hierarchy
    path("hierarchy/", PermissionHierarchyView.as_view(), name="hierarchy"),
    # Pending approvals
    path("approvals/", PendingApprovalsView.as_view(), name="pending_approvals"),
]
