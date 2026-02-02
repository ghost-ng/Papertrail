"""Tests for organizations models."""

import pytest
from django.contrib.auth import get_user_model

from apps.organizations.models import (
    Organization,
    Office,
    OrganizationMembership,
    OfficeMembership,
)

User = get_user_model()


@pytest.fixture
def organization(db):
    """Create a test organization."""
    return Organization.objects.create(code="USCC", name="US Cyber Command")


@pytest.fixture
def office(organization):
    """Create a test office."""
    return Office.objects.create(
        organization=organization,
        code="J0",
        name="Manpower & Personnel",
    )


@pytest.mark.django_db
class TestOrganization:
    """Tests for Organization model."""

    def test_create_organization(self):
        """Test creating an organization."""
        org = Organization.objects.create(code="test", name="Test Org")
        assert org.code == "TEST"  # Should be uppercased
        assert org.is_active

    def test_organization_str(self):
        """Test organization string representation."""
        org = Organization(code="USCC", name="US Cyber Command")
        assert str(org) == "USCC - US Cyber Command"


@pytest.mark.django_db
class TestOffice:
    """Tests for Office model."""

    def test_create_office(self, organization):
        """Test creating an office."""
        office = Office.objects.create(
            organization=organization,
            code="J1",
            name="Personnel",
        )
        assert office.organization == organization
        assert office.code == "J1"

    def test_office_str(self, organization):
        """Test office string representation."""
        office = Office(organization=organization, code="J0", name="Manpower")
        assert str(office) == "USCC J0"

    def test_office_display_name(self, organization):
        """Test office display_name property."""
        office = Office(organization=organization, code="J0", name="Manpower")
        assert office.display_name == "USCC J0 - Manpower"

    def test_office_hierarchy(self, organization):
        """Test office hierarchy methods."""
        parent = Office.objects.create(
            organization=organization,
            code="J2",
            name="Intel",
        )
        child = Office.objects.create(
            organization=organization,
            code="J2A",
            name="Analysis",
            parent=parent,
        )
        # Test ancestors
        ancestors = child.get_ancestors()
        assert len(ancestors) == 1
        assert parent in ancestors

        # Test descendants
        descendants = parent.get_descendants()
        assert len(descendants) == 1
        assert child in descendants

        # Test depth
        assert parent.get_depth() == 0
        assert child.get_depth() == 1


@pytest.mark.django_db
class TestOrganizationMembership:
    """Tests for OrganizationMembership model."""

    def test_create_membership(self, organization):
        """Test creating an org membership."""
        user = User.objects.create_user(email="test@example.com", password="test")
        membership = OrganizationMembership.objects.create(
            user=user,
            organization=organization,
        )
        assert membership.status == OrganizationMembership.STATUS_PENDING
        assert membership.role == OrganizationMembership.ROLE_MEMBER

    def test_is_approved(self, organization):
        """Test is_approved property."""
        user = User.objects.create_user(email="test@example.com", password="test")
        membership = OrganizationMembership.objects.create(
            user=user,
            organization=organization,
            status=OrganizationMembership.STATUS_APPROVED,
        )
        assert membership.is_approved is True

    def test_is_admin(self, organization):
        """Test is_admin property."""
        user = User.objects.create_user(email="test@example.com", password="test")
        membership = OrganizationMembership.objects.create(
            user=user,
            organization=organization,
            role=OrganizationMembership.ROLE_ADMIN,
            status=OrganizationMembership.STATUS_APPROVED,
        )
        assert membership.is_admin is True

        membership.status = OrganizationMembership.STATUS_PENDING
        assert membership.is_admin is False


@pytest.mark.django_db
class TestOfficeMembership:
    """Tests for OfficeMembership model."""

    def test_create_membership(self, office):
        """Test creating an office membership (immediate, no approval)."""
        user = User.objects.create_user(email="test@example.com", password="test")
        membership = OfficeMembership.objects.create(
            user=user,
            office=office,
        )
        # Membership is immediate - no status field
        assert membership.role == OfficeMembership.ROLE_MEMBER
        assert membership.joined_at is not None

    def test_is_admin(self, office):
        """Test is_admin property."""
        user = User.objects.create_user(email="test@example.com", password="test")
        membership = OfficeMembership.objects.create(
            user=user,
            office=office,
            role=OfficeMembership.ROLE_ADMIN,
        )
        assert membership.is_admin is True

        membership.role = OfficeMembership.ROLE_MEMBER
        assert membership.is_admin is False
