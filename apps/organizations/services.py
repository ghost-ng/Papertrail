"""Permission and hierarchy services for organizations."""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group

from .models import Office, OfficeMembership, Organization, OrganizationMembership

User = get_user_model()


class PermissionService:
    """
    Service for checking administrative permissions.

    Permission hierarchy:
    - System Admin (is_staff): Full system access
    - Org Admin: Manages ALL offices in their org
    - Office Admin: Manages their office + all descendants

    Office admins of ancestor offices have authority over descendant offices.
    """

    @staticmethod
    def is_system_admin(user) -> bool:
        """Check if user is a system administrator."""
        if not user.is_authenticated:
            return False
        if user.is_staff or user.is_superuser:
            return True
        return user.groups.filter(name="system_admins").exists()

    @staticmethod
    def is_org_admin(user, organization: Organization) -> bool:
        """Check if user is an admin of the given organization."""
        if not user.is_authenticated:
            return False
        if PermissionService.is_system_admin(user):
            return True
        return OrganizationMembership.objects.filter(
            user=user,
            organization=organization,
            role=OrganizationMembership.ROLE_ADMIN,
        ).exists()

    @staticmethod
    def is_office_admin(user, office: Office) -> bool:
        """
        Check if user can administer the given office.

        Returns True if:
        - User is a system admin
        - User is an org admin for the office's organization
        - User is an office admin for this office or any ancestor office
        """
        if not user.is_authenticated:
            return False

        # System admin
        if PermissionService.is_system_admin(user):
            return True

        # Org admin
        if PermissionService.is_org_admin(user, office.organization):
            return True

        # Office admin for this office or any ancestor
        office_ids = [office.pk] + [a.pk for a in office.get_ancestors()]
        return OfficeMembership.objects.filter(
            user=user,
            office_id__in=office_ids,
            role=OfficeMembership.ROLE_ADMIN,
        ).exists()

    @staticmethod
    def can_manage_office(user, office: Office) -> bool:
        """Alias for is_office_admin - can user manage this office?"""
        return PermissionService.is_office_admin(user, office)

    @staticmethod
    def can_create_sub_office(user, parent_office: Office) -> bool:
        """Check if user can create a sub-office under the given office."""
        return PermissionService.is_office_admin(user, parent_office)

    @staticmethod
    def can_add_office_member(user, office: Office) -> bool:
        """Check if user can add members to the given office."""
        return PermissionService.is_office_admin(user, office)

    @staticmethod
    def can_create_root_office(user, organization: Organization) -> bool:
        """Check if user can create a top-level office in the organization."""
        if not user.is_authenticated:
            return False
        if PermissionService.is_system_admin(user):
            return True
        return PermissionService.is_org_admin(user, organization)

    @staticmethod
    def get_manageable_offices(user) -> list:
        """
        Get all offices the user can manage.

        Returns offices where user is:
        - System admin (all offices)
        - Org admin (all offices in their orgs)
        - Office admin (that office + descendants)
        """
        if not user.is_authenticated:
            return []

        # System admin gets all
        if PermissionService.is_system_admin(user):
            return list(Office.objects.filter(is_active=True))

        manageable = set()

        # Org admin offices
        admin_orgs = OrganizationMembership.objects.filter(
            user=user,
            role=OrganizationMembership.ROLE_ADMIN,
        ).values_list("organization_id", flat=True)

        for office in Office.objects.filter(organization_id__in=admin_orgs, is_active=True):
            manageable.add(office)

        # Office admin offices + descendants
        admin_offices = OfficeMembership.objects.filter(
            user=user,
            role=OfficeMembership.ROLE_ADMIN,
        ).select_related("office")

        for membership in admin_offices:
            manageable.add(membership.office)
            for descendant in membership.office.get_descendants():
                manageable.add(descendant)

        return list(manageable)

    @staticmethod
    def get_user_offices(user) -> list:
        """Get all offices where user is a member (any role)."""
        if not user.is_authenticated:
            return []

        if user.is_superuser:
            return list(Office.objects.filter(is_active=True))

        return list(
            Office.objects.filter(
                memberships__user=user,
                is_active=True,
            )
        )


class HierarchyService:
    """Service for building and querying office hierarchies."""

    @staticmethod
    def get_office_tree(organization: Organization) -> list:
        """
        Get hierarchical tree of offices for an organization.

        Returns list of root offices with nested children structure.
        """
        offices = Office.objects.filter(
            organization=organization,
            is_active=True,
        ).select_related("parent").prefetch_related("memberships__user")

        # Build lookup
        office_map = {o.pk: o for o in offices}
        roots = []

        for office in offices:
            if office.parent_id is None:
                roots.append(office)

        return roots

    @staticmethod
    def build_nested_tree(organization: Organization) -> list:
        """
        Build a nested dictionary structure for the office tree.

        Returns list of dicts with 'office' and 'children' keys.
        """
        offices = list(
            Office.objects.filter(
                organization=organization,
                is_active=True,
            )
            .select_related("parent")
            .prefetch_related(
                "memberships__user",
                "children",
            )
        )

        # Build parent->children mapping
        children_map = {}
        roots = []

        for office in offices:
            children_map.setdefault(office.parent_id, []).append(office)

        def build_node(office):
            return {
                "office": office,
                "admins": office.memberships.filter(role=OfficeMembership.ROLE_ADMIN),
                "members": office.memberships.filter(role=OfficeMembership.ROLE_MEMBER),
                "children": [
                    build_node(child) for child in children_map.get(office.pk, [])
                ],
            }

        for office in children_map.get(None, []):
            roots.append(build_node(office))

        return roots
