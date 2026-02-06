"""URL configuration for organizations app."""

from django.urls import path

from . import views

app_name = "organizations"

urlpatterns = [
    # Organization views
    path("", views.OrganizationListView.as_view(), name="organization_list"),
    path("<int:pk>/", views.OrganizationDetailView.as_view(), name="organization_detail"),
    path("<int:pk>/edit/", views.OrganizationEditView.as_view(), name="organization_edit"),

    # Office views
    path("<int:org_pk>/offices/<int:pk>/", views.OfficeDetailView.as_view(), name="office_detail"),
    path("<int:org_pk>/offices/<int:pk>/edit/", views.OfficeEditView.as_view(), name="office_edit"),

    # Organization membership views (still has approval workflow)
    path("join/org/<int:org_pk>/", views.RequestOrgMembershipView.as_view(), name="request_org_membership"),
    path("memberships/org/<int:pk>/approve/", views.ApproveOrgMembershipView.as_view(), name="approve_org_membership"),

    # Office membership views
    path("join/office/<int:office_pk>/", views.RequestOfficeMembershipView.as_view(), name="request_office_membership"),
    path("memberships/office/<int:pk>/approve/", views.ApproveOfficeMembershipView.as_view(), name="approve_office_membership"),

    # Leave membership views
    path("leave/org/<int:org_pk>/", views.LeaveOrgMembershipView.as_view(), name="leave_org_membership"),
    path("leave/office/<int:office_pk>/", views.LeaveOfficeMembershipView.as_view(), name="leave_office_membership"),
]
