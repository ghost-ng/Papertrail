"""Views for organizations app."""

from django import forms
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.views.generic import ListView, DetailView, View, UpdateView

from apps.core.mixins import LoginRequiredMixin, AuditLogMixin
from apps.collaboration.models import Notification
from apps.collaboration.services import NotificationService

from .models import Organization, Office, OrganizationMembership, OfficeMembership


class OrganizationEditForm(forms.ModelForm):
    """Form for editing organization contact info."""

    class Meta:
        model = Organization
        fields = ["description", "contact_email", "contact_phone"]
        widgets = {
            "description": forms.Textarea(attrs={
                "rows": 3,
                "class": "mt-1 block w-full rounded-md border-gray-300 dark:border-gray-600 dark:bg-gray-700 dark:text-white shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm",
                "placeholder": "Brief description of this organization...",
            }),
            "contact_email": forms.EmailInput(attrs={
                "class": "mt-1 block w-full rounded-md border-gray-300 dark:border-gray-600 dark:bg-gray-700 dark:text-white shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm",
                "placeholder": "contact@example.com",
            }),
            "contact_phone": forms.TextInput(attrs={
                "class": "mt-1 block w-full rounded-md border-gray-300 dark:border-gray-600 dark:bg-gray-700 dark:text-white shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm",
                "placeholder": "+1 (555) 123-4567",
            }),
        }


class OfficeEditForm(forms.ModelForm):
    """Form for editing office contact info."""

    class Meta:
        model = Office
        fields = ["description", "contact_email", "contact_phone"]
        widgets = {
            "description": forms.Textarea(attrs={
                "rows": 3,
                "class": "mt-1 block w-full rounded-md border-gray-300 dark:border-gray-600 dark:bg-gray-700 dark:text-white shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm",
                "placeholder": "Brief description of this office...",
            }),
            "contact_email": forms.EmailInput(attrs={
                "class": "mt-1 block w-full rounded-md border-gray-300 dark:border-gray-600 dark:bg-gray-700 dark:text-white shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm",
                "placeholder": "office@example.com",
            }),
            "contact_phone": forms.TextInput(attrs={
                "class": "mt-1 block w-full rounded-md border-gray-300 dark:border-gray-600 dark:bg-gray-700 dark:text-white shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm",
                "placeholder": "+1 (555) 123-4567",
            }),
        }


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
        from .services import PermissionService

        context = super().get_context_data(**kwargs)
        context["offices"] = self.object.offices.filter(is_active=True, parent__isnull=True)
        context["user_membership"] = OrganizationMembership.objects.filter(
            user=self.request.user,
            organization=self.object,
        ).first()

        # Get approved members (managers and members)
        context["managers"] = OrganizationMembership.objects.filter(
            organization=self.object,
            role=OrganizationMembership.ROLE_MANAGER,
            status=OrganizationMembership.STATUS_APPROVED,
        ).select_related("user")[:10]

        context["members"] = OrganizationMembership.objects.filter(
            organization=self.object,
            role=OrganizationMembership.ROLE_MEMBER,
            status=OrganizationMembership.STATUS_APPROVED,
        ).select_related("user")[:10]

        # Check if user can approve memberships / edit organization
        is_org_manager = PermissionService.is_org_manager(self.request.user, self.object)
        context["can_approve"] = is_org_manager
        context["can_edit"] = is_org_manager or self.request.user.is_superuser

        # Get pending memberships if user can approve
        if context["can_approve"]:
            context["pending_memberships"] = OrganizationMembership.objects.filter(
                organization=self.object,
                status=OrganizationMembership.STATUS_PENDING,
            ).select_related("user")

        return context


class OfficeDetailView(LoginRequiredMixin, DetailView):
    """Office detail view."""

    model = Office
    template_name = "organizations/office_detail.html"
    context_object_name = "office"

    def get_context_data(self, **kwargs):
        from .services import PermissionService

        context = super().get_context_data(**kwargs)
        context["user_membership"] = OfficeMembership.objects.filter(
            user=self.request.user,
            office=self.object,
        ).first()

        # Get sub-offices
        context["sub_offices"] = self.object.children.filter(is_active=True)

        # Get approved members (managers and members)
        context["managers"] = OfficeMembership.objects.filter(
            office=self.object,
            role=OfficeMembership.ROLE_MANAGER,
            status=OfficeMembership.STATUS_APPROVED,
        ).select_related("user")[:10]

        context["members"] = OfficeMembership.objects.filter(
            office=self.object,
            role=OfficeMembership.ROLE_MEMBER,
            status=OfficeMembership.STATUS_APPROVED,
        ).select_related("user")[:10]

        # Check if user can approve memberships / edit office
        is_office_manager = PermissionService.is_office_manager(self.request.user, self.object)
        is_org_manager = PermissionService.is_org_manager(self.request.user, self.object.organization)
        context["can_approve"] = is_office_manager
        context["can_edit"] = is_office_manager or is_org_manager or self.request.user.is_superuser

        # Get pending memberships if user can approve
        if context["can_approve"]:
            context["pending_memberships"] = OfficeMembership.objects.filter(
                office=self.object,
                status=OfficeMembership.STATUS_PENDING,
            ).select_related("user")

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

        # Check permission: must be org manager
        can_approve = OrganizationMembership.objects.filter(
            user=request.user,
            organization=membership.organization,
            role=OrganizationMembership.ROLE_MANAGER,
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
            # Notify the user
            NotificationService.notify(
                user=membership.user,
                notification_type=Notification.NotificationType.MEMBERSHIP_APPROVED,
                title="Membership Approved",
                message=f"Your request to join {membership.organization.code} has been approved.",
                link=f"/organizations/{membership.organization.pk}/",
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
            # Notify the user
            reason_text = f" Reason: {membership.rejection_reason}" if membership.rejection_reason else ""
            NotificationService.notify(
                user=membership.user,
                notification_type=Notification.NotificationType.MEMBERSHIP_REJECTED,
                title="Membership Denied",
                message=f"Your request to join {membership.organization.code} has been denied.{reason_text}",
                link=f"/organizations/{membership.organization.pk}/",
            )

        return redirect("organizations:organization_detail", pk=membership.organization.pk)


class RequestOfficeMembershipView(LoginRequiredMixin, AuditLogMixin, View):
    """Request membership to an office."""

    def post(self, request, office_pk):
        office = get_object_or_404(Office, pk=office_pk, is_active=True)

        # Check if already a member
        existing = OfficeMembership.objects.filter(
            user=request.user,
            office=office,
        ).first()

        if existing:
            if existing.status == OfficeMembership.STATUS_APPROVED:
                messages.info(request, "You are already a member of this office.")
            elif existing.status == OfficeMembership.STATUS_PENDING:
                messages.info(request, "Your membership request is pending approval.")
            else:
                # Rejected - allow to request again
                existing.status = OfficeMembership.STATUS_PENDING
                existing.rejection_reason = ""
                existing.reviewed_at = None
                existing.reviewed_by = None
                existing.save()
                messages.success(request, "Membership request submitted.")
        else:
            OfficeMembership.objects.create(
                user=request.user,
                office=office,
                status=OfficeMembership.STATUS_PENDING,  # Requests start as pending
            )
            messages.success(request, "Membership request submitted.")
            self.log_action(
                action="office_membership_requested",
                resource_type="OfficeMembership",
                resource_id=f"{request.user.id}-{office.id}",
                organization=office.organization,
            )

        return redirect("organizations:office_detail", org_pk=office.organization.pk, pk=office_pk)


class ApproveOfficeMembershipView(LoginRequiredMixin, AuditLogMixin, View):
    """Approve or reject office membership request."""

    def post(self, request, pk):
        from .services import PermissionService

        membership = get_object_or_404(OfficeMembership, pk=pk)
        action = request.POST.get("action")

        # Check permission using PermissionService
        if not PermissionService.can_approve_office_membership(request.user, membership):
            messages.error(request, "You don't have permission to approve memberships.")
            return redirect("organizations:office_detail", org_pk=membership.office.organization.pk, pk=membership.office.pk)

        if action == "approve":
            membership.status = OfficeMembership.STATUS_APPROVED
            membership.reviewed_at = timezone.now()
            membership.reviewed_by = request.user
            membership.save()
            messages.success(request, f"Membership approved for {membership.user.email}.")
            self.log_action(
                action="office_membership_approved",
                resource_type="OfficeMembership",
                resource_id=str(membership.id),
                organization=membership.office.organization,
            )
            # Notify the user
            NotificationService.notify(
                user=membership.user,
                notification_type=Notification.NotificationType.MEMBERSHIP_APPROVED,
                title="Office Membership Approved",
                message=f"Your request to join {membership.office.display_name} has been approved.",
                link=f"/organizations/{membership.office.organization.pk}/offices/{membership.office.pk}/",
            )
        elif action == "reject":
            membership.status = OfficeMembership.STATUS_REJECTED
            membership.reviewed_at = timezone.now()
            membership.reviewed_by = request.user
            membership.rejection_reason = request.POST.get("reason", "")
            membership.save()
            messages.success(request, f"Membership rejected for {membership.user.email}.")
            self.log_action(
                action="office_membership_rejected",
                resource_type="OfficeMembership",
                resource_id=str(membership.id),
                organization=membership.office.organization,
            )
            # Notify the user
            reason_text = f" Reason: {membership.rejection_reason}" if membership.rejection_reason else ""
            NotificationService.notify(
                user=membership.user,
                notification_type=Notification.NotificationType.MEMBERSHIP_REJECTED,
                title="Office Membership Denied",
                message=f"Your request to join {membership.office.display_name} has been denied.{reason_text}",
                link=f"/organizations/{membership.office.organization.pk}/offices/{membership.office.pk}/",
            )

        return redirect("organizations:office_detail", org_pk=membership.office.organization.pk, pk=membership.office.pk)


class OrganizationEditView(LoginRequiredMixin, AuditLogMixin, UpdateView):
    """Edit organization contact info. Only org managers can edit."""

    model = Organization
    form_class = OrganizationEditForm
    template_name = "organizations/organization_edit.html"
    context_object_name = "organization"

    def dispatch(self, request, *args, **kwargs):
        from .services import PermissionService

        self.object = self.get_object()
        # Check permission: org managers or system admins
        if not (
            PermissionService.is_org_manager(request.user, self.object)
            or request.user.is_superuser
        ):
            messages.error(request, "You don't have permission to edit this organization.")
            return redirect("organizations:organization_detail", pk=self.object.pk)
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        messages.success(self.request, "Organization updated successfully.")
        self.log_action(
            action="organization_updated",
            resource_type="Organization",
            resource_id=str(self.object.id),
            organization=self.object,
        )
        return super().form_valid(form)

    def get_success_url(self):
        return self.object.get_absolute_url()


class OfficeEditView(LoginRequiredMixin, AuditLogMixin, UpdateView):
    """Edit office contact info. Office managers and org managers can edit."""

    model = Office
    form_class = OfficeEditForm
    template_name = "organizations/office_edit.html"
    context_object_name = "office"

    def dispatch(self, request, *args, **kwargs):
        from .services import PermissionService

        self.object = self.get_object()
        # Check permission: office managers, org managers, or system admins
        if not (
            PermissionService.is_office_manager(request.user, self.object)
            or PermissionService.is_org_manager(request.user, self.object.organization)
            or request.user.is_superuser
        ):
            messages.error(request, "You don't have permission to edit this office.")
            return redirect(
                "organizations:office_detail",
                org_pk=self.object.organization.pk,
                pk=self.object.pk,
            )
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        messages.success(self.request, "Office updated successfully.")
        self.log_action(
            action="office_updated",
            resource_type="Office",
            resource_id=str(self.object.id),
            organization=self.object.organization,
        )
        return super().form_valid(form)

    def get_success_url(self):
        return self.object.get_absolute_url()


class LeaveOrgMembershipView(LoginRequiredMixin, AuditLogMixin, View):
    """Allow a user to leave an organization."""

    def post(self, request, org_pk):
        organization = get_object_or_404(Organization, pk=org_pk)

        membership = OrganizationMembership.objects.filter(
            user=request.user,
            organization=organization,
        ).first()

        if not membership:
            messages.error(request, "You are not a member of this organization.")
            return redirect("organizations:organization_detail", pk=org_pk)

        # Delete the membership
        membership.delete()
        messages.success(request, f"You have left {organization.code}.")
        self.log_action(
            action="membership_left",
            resource_type="OrganizationMembership",
            resource_id=f"{request.user.id}-{organization.id}",
            organization=organization,
        )

        return redirect("organizations:organization_detail", pk=org_pk)


class LeaveOfficeMembershipView(LoginRequiredMixin, AuditLogMixin, View):
    """Allow a user to leave an office."""

    def post(self, request, office_pk):
        office = get_object_or_404(Office, pk=office_pk)

        membership = OfficeMembership.objects.filter(
            user=request.user,
            office=office,
        ).first()

        if not membership:
            messages.error(request, "You are not a member of this office.")
            return redirect("organizations:office_detail", org_pk=office.organization.pk, pk=office_pk)

        # Delete the membership
        membership.delete()
        messages.success(request, f"You have left {office.display_name}.")
        self.log_action(
            action="office_membership_left",
            resource_type="OfficeMembership",
            resource_id=f"{request.user.id}-{office.id}",
            organization=office.organization,
        )

        return redirect("organizations:office_detail", org_pk=office.organization.pk, pk=office_pk)
