"""Permission and hierarchy services for organizations."""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group

from .models import Office, OfficeMembership, Organization, OrganizationMembership

User = get_user_model()


class PermissionService:
    """
    Service for checking management permissions.

    Permission hierarchy:
    - System Admin (is_staff): Full system access
    - Org Manager: Manages ALL offices in their org
    - Office Manager: Manages their office + all descendants

    Office managers of ancestor offices have authority over descendant offices.
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
    def is_org_manager(user, organization: Organization) -> bool:
        """Check if user is a manager of the given organization."""
        if not user.is_authenticated:
            return False
        if PermissionService.is_system_admin(user):
            return True
        return OrganizationMembership.objects.filter(
            user=user,
            organization=organization,
            role=OrganizationMembership.ROLE_MANAGER,
            status=OrganizationMembership.STATUS_APPROVED,
        ).exists()

    @staticmethod
    def is_office_manager(user, office: Office) -> bool:
        """
        Check if user can manage the given office.

        Returns True if:
        - User is a system admin
        - User is an org manager for the office's organization
        - User is an office manager for this office or any ancestor office
        """
        if not user.is_authenticated:
            return False

        # System admin
        if PermissionService.is_system_admin(user):
            return True

        # Org manager
        if PermissionService.is_org_manager(user, office.organization):
            return True

        # Office manager for this office or any ancestor
        office_ids = [office.pk] + [a.pk for a in office.get_ancestors()]
        return OfficeMembership.objects.filter(
            user=user,
            office_id__in=office_ids,
            role=OfficeMembership.ROLE_MANAGER,
            status=OfficeMembership.STATUS_APPROVED,
        ).exists()

    @staticmethod
    def can_manage_office(user, office: Office) -> bool:
        """Alias for is_office_manager - can user manage this office?"""
        return PermissionService.is_office_manager(user, office)

    @staticmethod
    def can_create_sub_office(user, parent_office: Office) -> bool:
        """Check if user can create a sub-office under the given office."""
        return PermissionService.is_office_manager(user, parent_office)

    @staticmethod
    def can_add_office_member(user, office: Office) -> bool:
        """Check if user can add members to the given office."""
        return PermissionService.is_office_manager(user, office)

    @staticmethod
    def can_create_root_office(user, organization: Organization) -> bool:
        """Check if user can create a top-level office in the organization."""
        if not user.is_authenticated:
            return False
        if PermissionService.is_system_admin(user):
            return True
        return PermissionService.is_org_manager(user, organization)

    @staticmethod
    def get_manageable_offices(user) -> list:
        """
        Get all offices the user can manage.

        Returns offices where user is:
        - System admin (all offices)
        - Org manager (all offices in their orgs)
        - Office manager (that office + descendants)
        """
        if not user.is_authenticated:
            return []

        # System admin gets all
        if PermissionService.is_system_admin(user):
            return list(Office.objects.filter(is_active=True))

        manageable = set()

        # Org manager offices
        manager_orgs = OrganizationMembership.objects.filter(
            user=user,
            role=OrganizationMembership.ROLE_MANAGER,
            status=OrganizationMembership.STATUS_APPROVED,
        ).values_list("organization_id", flat=True)

        for office in Office.objects.filter(organization_id__in=manager_orgs, is_active=True):
            manageable.add(office)

        # Office manager offices + descendants
        manager_offices = OfficeMembership.objects.filter(
            user=user,
            role=OfficeMembership.ROLE_MANAGER,
            status=OfficeMembership.STATUS_APPROVED,
        ).select_related("office")

        for membership in manager_offices:
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
                memberships__status=OfficeMembership.STATUS_APPROVED,
                is_active=True,
            )
        )

    @staticmethod
    def get_user_organizations(user) -> list:
        """Get all organizations where user has approved membership."""
        if not user.is_authenticated:
            return []

        if user.is_superuser:
            return list(Organization.objects.filter(is_active=True))

        return list(
            Organization.objects.filter(
                memberships__user=user,
                memberships__status=OrganizationMembership.STATUS_APPROVED,
                is_active=True,
            ).distinct()
        )

    # Workflow Permission Methods

    @staticmethod
    def can_create_workflow(user, organization: Organization = None) -> bool:
        """
        Check if user can create workflow templates.

        System admins, org managers, and office managers can create workflows.
        If organization is specified, checks permission for that org.
        """
        if not user.is_authenticated:
            return False

        if PermissionService.is_system_admin(user):
            return True

        if organization:
            # Check if org manager for this org
            if PermissionService.is_org_manager(user, organization):
                return True
            # Check if office manager in this org
            return OfficeMembership.objects.filter(
                user=user,
                office__organization=organization,
                role=OfficeMembership.ROLE_MANAGER,
                status=OfficeMembership.STATUS_APPROVED,
            ).exists()

        # Check if manager anywhere
        has_org_manager = OrganizationMembership.objects.filter(
            user=user,
            role=OrganizationMembership.ROLE_MANAGER,
            status=OrganizationMembership.STATUS_APPROVED,
        ).exists()

        has_office_manager = OfficeMembership.objects.filter(
            user=user,
            role=OfficeMembership.ROLE_MANAGER,
            status=OfficeMembership.STATUS_APPROVED,
        ).exists()

        return has_org_manager or has_office_manager

    @staticmethod
    def can_edit_workflow(user, workflow) -> bool:
        """Check if user can edit a workflow template."""
        if not user.is_authenticated:
            return False

        if PermissionService.is_system_admin(user):
            return True

        # Creator can always edit their own workflows
        if workflow.created_by_id == user.pk:
            return True

        # Org manager can edit workflows in their org
        if workflow.organization:
            return PermissionService.is_org_manager(user, workflow.organization)

        return False

    @staticmethod
    def can_duplicate_workflow(user, workflow) -> bool:
        """Check if user can duplicate a workflow template."""
        if not user.is_authenticated:
            return False

        # Must be able to create workflows AND view the source workflow
        return (
            PermissionService.can_create_workflow(user)
            and PermissionService.can_view_workflow(user, workflow)
        )

    @staticmethod
    def can_view_workflow(user, workflow) -> bool:
        """Check if user can view a workflow template."""
        if not user.is_authenticated:
            return False

        if PermissionService.is_system_admin(user):
            return True

        # System workflows (no org) are visible to all authenticated users
        if workflow.organization is None:
            return True

        # Org-specific workflows visible to org members
        return OrganizationMembership.objects.filter(
            user=user,
            organization=workflow.organization,
            status=OrganizationMembership.STATUS_APPROVED,
        ).exists()

    @staticmethod
    def get_viewable_workflows(user, queryset):
        """
        Filter workflow queryset to only those viewable by user.

        Returns workflows where:
        - User is system admin (all workflows)
        - Workflow has no org (system-level workflows)
        - User is member of the workflow's org
        """
        if not user.is_authenticated:
            return queryset.none()

        if PermissionService.is_system_admin(user):
            return queryset

        # Get user's approved org memberships
        user_org_ids = OrganizationMembership.objects.filter(
            user=user,
            status=OrganizationMembership.STATUS_APPROVED,
        ).values_list("organization_id", flat=True)

        # System workflows (no org) + workflows from user's orgs
        from django.db.models import Q
        return queryset.filter(
            Q(organization__isnull=True) | Q(organization_id__in=user_org_ids)
        )

    # Membership Approval Methods

    @staticmethod
    def can_approve_org_membership(user, membership) -> bool:
        """Check if user can approve/reject an organization membership request."""
        if not user.is_authenticated:
            return False

        if PermissionService.is_system_admin(user):
            return True

        # Org managers can approve memberships for their org
        return PermissionService.is_org_manager(user, membership.organization)

    @staticmethod
    def can_approve_office_membership(user, membership) -> bool:
        """Check if user can approve/reject an office membership request."""
        if not user.is_authenticated:
            return False

        if PermissionService.is_system_admin(user):
            return True

        # Org managers can approve office memberships in their org
        if PermissionService.is_org_manager(user, membership.office.organization):
            return True

        # Office managers can approve memberships for their office
        return PermissionService.is_office_manager(user, membership.office)

    @staticmethod
    def get_pending_org_memberships(user):
        """Get organization memberships pending approval that user can approve."""
        if not user.is_authenticated:
            return OrganizationMembership.objects.none()

        pending = OrganizationMembership.objects.filter(
            status=OrganizationMembership.STATUS_PENDING
        ).select_related("user", "organization")

        if PermissionService.is_system_admin(user):
            return pending

        # Get orgs where user is a manager
        manager_org_ids = OrganizationMembership.objects.filter(
            user=user,
            role=OrganizationMembership.ROLE_MANAGER,
            status=OrganizationMembership.STATUS_APPROVED,
        ).values_list("organization_id", flat=True)

        return pending.filter(organization_id__in=manager_org_ids)

    @staticmethod
    def get_pending_office_memberships(user):
        """Get office memberships pending approval that user can approve."""
        if not user.is_authenticated:
            return OfficeMembership.objects.none()

        pending = OfficeMembership.objects.filter(
            status=OfficeMembership.STATUS_PENDING
        ).select_related("user", "office", "office__organization")

        if PermissionService.is_system_admin(user):
            return pending

        # Get orgs where user is org manager
        manager_org_ids = OrganizationMembership.objects.filter(
            user=user,
            role=OrganizationMembership.ROLE_MANAGER,
            status=OrganizationMembership.STATUS_APPROVED,
        ).values_list("organization_id", flat=True)

        # Get offices where user is office manager
        manager_office_ids = OfficeMembership.objects.filter(
            user=user,
            role=OfficeMembership.ROLE_MANAGER,
            status=OfficeMembership.STATUS_APPROVED,
        ).values_list("office_id", flat=True)

        # Include descendant office IDs
        all_manager_office_ids = set(manager_office_ids)
        for office_id in manager_office_ids:
            try:
                office = Office.objects.get(pk=office_id)
                for descendant in office.get_descendants():
                    all_manager_office_ids.add(descendant.pk)
            except Office.DoesNotExist:
                pass

        from django.db.models import Q
        return pending.filter(
            Q(office__organization_id__in=manager_org_ids)
            | Q(office_id__in=all_manager_office_ids)
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
                "managers": office.memberships.filter(
                    role=OfficeMembership.ROLE_MANAGER,
                    status=OfficeMembership.STATUS_APPROVED,
                ),
                "members": office.memberships.filter(
                    role=OfficeMembership.ROLE_MEMBER,
                    status=OfficeMembership.STATUS_APPROVED,
                ),
                "children": [
                    build_node(child) for child in children_map.get(office.pk, [])
                ],
            }

        for office in children_map.get(None, []):
            roots.append(build_node(office))

        return roots
