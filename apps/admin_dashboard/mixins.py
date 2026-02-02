"""Mixins for admin dashboard access control."""

from django.contrib.auth.mixins import UserPassesTestMixin


class SystemAdminRequiredMixin(UserPassesTestMixin):
    """Require user to be a system admin (staff or in system_admins group)."""

    def test_func(self):
        """Check if user has system admin permissions."""
        user = self.request.user
        if not user.is_authenticated:
            return False
        if user.is_superuser or user.is_staff:
            return True
        return user.groups.filter(name="system_admins").exists()

    def get_context_data(self, **kwargs):
        """Add admin navigation context."""
        context = super().get_context_data(**kwargs)
        context["is_system_admin"] = True
        return context


class OrgAdminRequiredMixin(UserPassesTestMixin):
    """Require user to be an org admin for the specified organization."""

    def test_func(self):
        """Check if user has org admin permissions."""
        user = self.request.user
        if not user.is_authenticated:
            return False
        if user.is_superuser or user.is_staff:
            return True
        if user.groups.filter(name="system_admins").exists():
            return True

        # Check org_admin role via OrganizationMembership
        org_id = self.kwargs.get("org_id") or self.request.GET.get("org_id")
        if org_id:
            from apps.organizations.models import OrganizationMembership

            return OrganizationMembership.objects.filter(
                user=user,
                organization_id=org_id,
                role=OrganizationMembership.ROLE_ADMIN,
                status=OrganizationMembership.STATUS_APPROVED,
            ).exists()
        return False


class OfficeAdminRequiredMixin(UserPassesTestMixin):
    """
    Require user to be an office admin for the specified office.

    Checks:
    - System admin (superuser, staff, system_admins group)
    - Org admin for the office's organization
    - Office admin for the office OR any ancestor office
    """

    def test_func(self):
        """Check if user has office admin permissions."""
        user = self.request.user
        if not user.is_authenticated:
            return False
        if user.is_superuser or user.is_staff:
            return True
        if user.groups.filter(name="system_admins").exists():
            return True

        office_id = self.kwargs.get("office_id") or self.request.GET.get("office_id")
        if not office_id:
            return False

        from apps.organizations.models import Office, OfficeMembership, OrganizationMembership

        try:
            office = Office.objects.get(pk=office_id)
        except Office.DoesNotExist:
            return False

        # Check if user is org admin for this office's organization
        if OrganizationMembership.objects.filter(
            user=user,
            organization=office.organization,
            role=OrganizationMembership.ROLE_ADMIN,
            status=OrganizationMembership.STATUS_APPROVED,
        ).exists():
            return True

        # Check if user is office admin for this office OR any ancestor
        office_ids = [office.pk] + [a.pk for a in office.get_ancestors()]
        return OfficeMembership.objects.filter(
            user=user,
            office_id__in=office_ids,
            role=OfficeMembership.ROLE_ADMIN,
        ).exists()


# Backwards compatibility alias
OfficeManagerRequiredMixin = OfficeAdminRequiredMixin
