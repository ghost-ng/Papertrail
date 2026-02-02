"""Views for organizations app."""

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.views.generic import ListView, DetailView, View

from apps.core.mixins import LoginRequiredMixin, AuditLogMixin

from .models import Organization, Office, OrganizationMembership, OfficeMembership


class OrganizationListView(LoginRequiredMixin, ListView):
    """List all organizations."""

    model = Organization
    template_name = "organizations/organization_list.html"
    context_object_name = "organizations"

    def get_queryset(self):
        return Organization.objects.filter(is_active=True)


class OrganizationDetailView(LoginRequiredMixin, DetailView):
    """Organization detail view."""

    model = Organization
    template_name = "organizations/organization_detail.html"
    context_object_name = "organization"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["offices"] = self.object.offices.filter(is_active=True)
        context["user_membership"] = OrganizationMembership.objects.filter(
            user=self.request.user,
            organization=self.object,
        ).first()
        return context


class OfficeDetailView(LoginRequiredMixin, DetailView):
    """Office detail view."""

    model = Office
    template_name = "organizations/office_detail.html"
    context_object_name = "office"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["user_membership"] = OfficeMembership.objects.filter(
            user=self.request.user,
            office=self.object,
        ).first()
        return context


class RequestOrgMembershipView(LoginRequiredMixin, AuditLogMixin, View):
    """Request membership to an organization."""

    def post(self, request, org_pk):
        organization = get_object_or_404(Organization, pk=org_pk, is_active=True)

        # Check if already a member
        existing = OrganizationMembership.objects.filter(
            user=request.user,
            organization=organization,
        ).first()

        if existing:
            if existing.status == OrganizationMembership.STATUS_APPROVED:
                messages.info(request, "You are already a member of this organization.")
            elif existing.status == OrganizationMembership.STATUS_PENDING:
                messages.info(request, "Your membership request is pending approval.")
            else:
                # Rejected - allow to request again
                existing.status = OrganizationMembership.STATUS_PENDING
                existing.rejection_reason = ""
                existing.reviewed_at = None
                existing.reviewed_by = None
                existing.save()
                messages.success(request, "Membership request submitted.")
        else:
            OrganizationMembership.objects.create(
                user=request.user,
                organization=organization,
            )
            messages.success(request, "Membership request submitted.")
            self.log_action(
                action="membership_requested",
                resource_type="OrganizationMembership",
                resource_id=f"{request.user.id}-{organization.id}",
                organization=organization,
            )

        return redirect("organizations:organization_detail", pk=org_pk)


class ApproveOrgMembershipView(LoginRequiredMixin, AuditLogMixin, View):
    """Approve or reject organization membership request."""

    def post(self, request, pk):
        membership = get_object_or_404(OrganizationMembership, pk=pk)
        action = request.POST.get("action")

        # Check permission: must be org admin
        can_approve = OrganizationMembership.objects.filter(
            user=request.user,
            organization=membership.organization,
            role=OrganizationMembership.ROLE_ADMIN,
            status=OrganizationMembership.STATUS_APPROVED,
        ).exists()

        if not can_approve and not request.user.is_superuser:
            messages.error(request, "You don't have permission to approve memberships.")
            return redirect("organizations:organization_detail", pk=membership.organization.pk)

        if action == "approve":
            membership.status = OrganizationMembership.STATUS_APPROVED
            membership.reviewed_at = timezone.now()
            membership.reviewed_by = request.user
            membership.save()
            messages.success(request, f"Membership approved for {membership.user.email}.")
            self.log_action(
                action="membership_approved",
                resource_type="OrganizationMembership",
                resource_id=str(membership.id),
                organization=membership.organization,
            )
        elif action == "reject":
            membership.status = OrganizationMembership.STATUS_REJECTED
            membership.reviewed_at = timezone.now()
            membership.reviewed_by = request.user
            membership.rejection_reason = request.POST.get("reason", "")
            membership.save()
            messages.success(request, f"Membership rejected for {membership.user.email}.")
            self.log_action(
                action="membership_rejected",
                resource_type="OrganizationMembership",
                resource_id=str(membership.id),
                organization=membership.organization,
            )

        return redirect("organizations:organization_detail", pk=membership.organization.pk)


# NOTE: Office membership is immediate (no approval workflow).
# Users are added to offices by admins via the admin dashboard.
# The following views have been removed:
# - RequestOfficeMembershipView
# - ApproveOfficeMembershipView
