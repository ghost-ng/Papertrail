"""Tests for accounts models."""

import pytest
from django.contrib.auth import get_user_model

User = get_user_model()


@pytest.mark.django_db
class TestUserModel:
    """Tests for User model."""

    def test_create_user_with_email(self):
        """Test creating a user with email."""
        user = User.objects.create_user(
            email="test@example.com",
            password="testpass123",
            first_name="Test",
            last_name="User",
        )
        assert user.email == "test@example.com"
        assert user.check_password("testpass123")
        assert user.is_active
        assert not user.is_staff
        assert not user.is_superuser

    def test_create_user_without_email_raises_error(self):
        """Test that creating a user without email raises ValueError."""
        with pytest.raises(ValueError, match="Email field must be set"):
            User.objects.create_user(email="", password="testpass123")

    def test_create_superuser(self):
        """Test creating a superuser."""
        user = User.objects.create_superuser(
            email="admin@example.com",
            password="adminpass123",
        )
        assert user.is_staff
        assert user.is_superuser
        assert user.is_active

    def test_full_name_property(self):
        """Test full_name property."""
        user = User(email="test@example.com", first_name="John", last_name="Doe")
        assert user.full_name == "John Doe"

    def test_full_name_falls_back_to_email(self):
        """Test full_name falls back to email when name is empty."""
        user = User(email="test@example.com")
        assert user.full_name == "test@example.com"

    def test_is_pki_user_property(self):
        """Test is_pki_user property."""
        user = User(email="test@example.com", auth_method=User.AUTH_METHOD_PKI)
        assert user.is_pki_user

        user.auth_method = User.AUTH_METHOD_PASSWORD
        assert not user.is_pki_user

    def test_has_valid_pki_property(self):
        """Test has_valid_pki property."""
        user = User(
            email="test@example.com",
            auth_method=User.AUTH_METHOD_PKI,
            pki_status=User.PKI_STATUS_APPROVED,
        )
        assert user.has_valid_pki

        user.pki_status = User.PKI_STATUS_PENDING
        assert not user.has_valid_pki

    def test_has_signing_capability_pki_user(self):
        """Test has_signing_capability for PKI user."""
        user = User(
            email="test@example.com",
            auth_method=User.AUTH_METHOD_PKI,
            pki_status=User.PKI_STATUS_APPROVED,
        )
        assert user.has_signing_capability

    def test_has_signing_capability_pgp_user(self):
        """Test has_signing_capability for PGP user."""
        user = User(
            email="test@example.com",
            auth_method=User.AUTH_METHOD_PASSWORD,
            pgp_public_key="-----BEGIN PGP PUBLIC KEY BLOCK-----",
            pgp_private_key_encrypted=b"encrypted_key",
        )
        assert user.has_signing_capability

        user.pgp_public_key = ""
        assert not user.has_signing_capability
