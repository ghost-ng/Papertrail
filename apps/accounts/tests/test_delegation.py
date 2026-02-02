"""Tests for the Delegation model."""

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.accounts.models import Delegation, User
from apps.organizations.models import Office, Organization


@pytest.fixture
def organization():
    """Create a test organization."""
    return Organization.objects.create(
        code="TEST",
        name="Test Organization",
    )


@pytest.fixture
def office(organization):
    """Create a test office."""
    return Office.objects.create(
        organization=organization,
        code="OFF1",
        name="Test Office 1",
    )


@pytest.fixture
def office2(organization):
    """Create a second test office."""
    return Office.objects.create(
        organization=organization,
        code="OFF2",
        name="Test Office 2",
    )


@pytest.fixture
def delegator():
    """Create a delegator user."""
    return User.objects.create_user(
        email="delegator@example.com",
        password="testpass123",
        first_name="Delegator",
        last_name="User",
    )


@pytest.fixture
def delegate():
    """Create a delegate user."""
    return User.objects.create_user(
        email="delegate@example.com",
        password="testpass123",
        first_name="Delegate",
        last_name="User",
    )


@pytest.mark.django_db
class TestDelegationModel:
    """Tests for Delegation model."""

    def test_create_delegation(self, delegator, delegate):
        """Test creating a basic delegation."""
        today = timezone.now().date()
        delegation = Delegation.objects.create(
            delegator=delegator,
            delegate=delegate,
            start_date=today,
            end_date=today + timedelta(days=7),
            reason="On vacation",
        )

        assert delegation.delegator == delegator
        assert delegation.delegate == delegate
        assert delegation.start_date == today
        assert delegation.end_date == today + timedelta(days=7)
        assert delegation.all_offices is True
        assert delegation.can_complete is True
        assert delegation.can_return is True
        assert delegation.can_sign is False
        assert delegation.is_active is True
        assert delegation.reason == "On vacation"

    def test_str_representation(self, delegator, delegate):
        """Test the string representation of a delegation."""
        today = timezone.now().date()
        end_date = today + timedelta(days=7)
        delegation = Delegation.objects.create(
            delegator=delegator,
            delegate=delegate,
            start_date=today,
            end_date=end_date,
        )

        expected = f"{delegator.email} -> {delegate.email} ({today} to {end_date})"
        assert str(delegation) == expected

    def test_is_currently_active_when_active(self, delegator, delegate):
        """Test is_currently_active returns True for active delegation within date range."""
        today = timezone.now().date()
        delegation = Delegation.objects.create(
            delegator=delegator,
            delegate=delegate,
            start_date=today - timedelta(days=1),
            end_date=today + timedelta(days=7),
            is_active=True,
        )

        assert delegation.is_currently_active is True

    def test_is_currently_active_future_delegation(self, delegator, delegate):
        """Test is_currently_active returns False for future delegation."""
        today = timezone.now().date()
        delegation = Delegation.objects.create(
            delegator=delegator,
            delegate=delegate,
            start_date=today + timedelta(days=1),
            end_date=today + timedelta(days=7),
            is_active=True,
        )

        assert delegation.is_currently_active is False

    def test_is_currently_active_past_delegation(self, delegator, delegate):
        """Test is_currently_active returns False for past delegation."""
        today = timezone.now().date()
        delegation = Delegation.objects.create(
            delegator=delegator,
            delegate=delegate,
            start_date=today - timedelta(days=14),
            end_date=today - timedelta(days=7),
            is_active=True,
        )

        assert delegation.is_currently_active is False

    def test_is_currently_active_when_deactivated(self, delegator, delegate):
        """Test is_currently_active returns False when is_active is False."""
        today = timezone.now().date()
        delegation = Delegation.objects.create(
            delegator=delegator,
            delegate=delegate,
            start_date=today - timedelta(days=1),
            end_date=today + timedelta(days=7),
            is_active=False,
        )

        assert delegation.is_currently_active is False

    def test_get_active_delegation(self, delegator, delegate):
        """Test get_active_delegation returns active delegation."""
        today = timezone.now().date()
        delegation = Delegation.objects.create(
            delegator=delegator,
            delegate=delegate,
            start_date=today - timedelta(days=1),
            end_date=today + timedelta(days=7),
            is_active=True,
        )

        result = Delegation.get_active_delegation(delegator)
        assert result == delegation

    def test_get_active_delegation_returns_none_for_inactive(self, delegator, delegate):
        """Test get_active_delegation returns None when no active delegation."""
        today = timezone.now().date()
        Delegation.objects.create(
            delegator=delegator,
            delegate=delegate,
            start_date=today - timedelta(days=1),
            end_date=today + timedelta(days=7),
            is_active=False,
        )

        result = Delegation.get_active_delegation(delegator)
        assert result is None

    def test_get_active_delegation_returns_none_for_expired(self, delegator, delegate):
        """Test get_active_delegation returns None for expired delegation."""
        today = timezone.now().date()
        Delegation.objects.create(
            delegator=delegator,
            delegate=delegate,
            start_date=today - timedelta(days=14),
            end_date=today - timedelta(days=7),
            is_active=True,
        )

        result = Delegation.get_active_delegation(delegator)
        assert result is None

    def test_get_active_delegation_specific_office_all_offices(
        self, delegator, delegate, office
    ):
        """Test get_active_delegation with office filter when all_offices is True."""
        today = timezone.now().date()
        delegation = Delegation.objects.create(
            delegator=delegator,
            delegate=delegate,
            start_date=today - timedelta(days=1),
            end_date=today + timedelta(days=7),
            is_active=True,
            all_offices=True,
        )

        result = Delegation.get_active_delegation(delegator, office=office)
        assert result == delegation

    def test_get_active_delegation_specific_office_match(
        self, delegator, delegate, office
    ):
        """Test get_active_delegation with office filter for specific office match."""
        today = timezone.now().date()
        delegation = Delegation.objects.create(
            delegator=delegator,
            delegate=delegate,
            start_date=today - timedelta(days=1),
            end_date=today + timedelta(days=7),
            is_active=True,
            all_offices=False,
        )
        delegation.specific_offices.add(office)

        result = Delegation.get_active_delegation(delegator, office=office)
        assert result == delegation

    def test_get_active_delegation_specific_office_no_match(
        self, delegator, delegate, office, office2
    ):
        """Test get_active_delegation returns None when office doesn't match."""
        today = timezone.now().date()
        delegation = Delegation.objects.create(
            delegator=delegator,
            delegate=delegate,
            start_date=today - timedelta(days=1),
            end_date=today + timedelta(days=7),
            is_active=True,
            all_offices=False,
        )
        delegation.specific_offices.add(office)

        # Query for office2 which is not in the delegation's specific_offices
        result = Delegation.get_active_delegation(delegator, office=office2)
        assert result is None

    def test_delegation_related_names(self, delegator, delegate):
        """Test related names work correctly."""
        today = timezone.now().date()
        delegation = Delegation.objects.create(
            delegator=delegator,
            delegate=delegate,
            start_date=today,
            end_date=today + timedelta(days=7),
        )

        assert delegation in delegator.delegations_given.all()
        assert delegation in delegate.delegations_received.all()

    def test_delegation_ordering(self, delegator, delegate):
        """Test delegations are ordered by start_date descending."""
        today = timezone.now().date()
        delegation1 = Delegation.objects.create(
            delegator=delegator,
            delegate=delegate,
            start_date=today - timedelta(days=30),
            end_date=today - timedelta(days=23),
        )
        delegation2 = Delegation.objects.create(
            delegator=delegator,
            delegate=delegate,
            start_date=today,
            end_date=today + timedelta(days=7),
        )
        delegation3 = Delegation.objects.create(
            delegator=delegator,
            delegate=delegate,
            start_date=today - timedelta(days=15),
            end_date=today - timedelta(days=8),
        )

        delegations = list(Delegation.objects.all())
        assert delegations[0] == delegation2  # Most recent start_date first
        assert delegations[1] == delegation3
        assert delegations[2] == delegation1
