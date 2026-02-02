"""URL configuration for Papertrail project."""

from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("apps.core.urls")),
    path("accounts/", include("apps.accounts.urls")),
    path("organizations/", include("apps.organizations.urls")),
    path("packages/", include("apps.packages.urls")),
    path("collaboration/", include("apps.collaboration.urls")),
    path("admin-dashboard/", include("apps.admin_dashboard.urls")),
]
