"""URL configuration for organizations app."""

from django.urls import path

from . import views

app_name = "organizations"

urlpatterns = [
    # Organization views
    path("", views.OrganizationListView.as_view(), name="organization_list"),
    path("<int:pk>/", views.OrganizationDetailView.as_view(), name="organization_detail"),

    # Office views
    path("<int:org_pk>/offices/<int:pk>/", views.OfficeDetailView.as_view(), name="office_detail"),

    # Organization membership views (still has approval workflow)
    path("join/org/<int:org_pk>/", views.RequestOrgMembershipView.as_view(), name="request_org_membership"),
    path("memberships/org/<int:pk>/approve/", views.ApproveOrgMembershipView.as_view(), name="approve_org_membership"),

    # NOTE: Office membership is immediate - no request/approve views needed.
    # Users are added via admin dashboard by office admins.
]
