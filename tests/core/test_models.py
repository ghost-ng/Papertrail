"""Tests for core models."""

import pytest
from django.contrib.auth import get_user_model

from apps.core.models import AuditLog, SystemSetting

User = get_user_model()


@pytest.mark.django_db
class TestAuditLog:
    """Tests for AuditLog model."""

    def test_create_audit_log(self):
        """Test creating an audit log entry."""
        log = AuditLog.objects.create(
            action="created",
            resource_type="Package",
            resource_id="123",
        )
        assert log.id is not None
        assert log.action == "created"
        assert log.resource_type == "Package"

    def test_audit_log_cannot_be_modified(self):
        """Test that audit logs cannot be modified after creation."""
        log = AuditLog.objects.create(
            action="created",
            resource_type="Package",
            resource_id="123",
        )
        log.action = "updated"
        with pytest.raises(ValueError, match="cannot be modified"):
            log.save()

    def test_audit_log_cannot_be_deleted(self):
        """Test that audit logs cannot be deleted."""
        log = AuditLog.objects.create(
            action="created",
            resource_type="Package",
            resource_id="123",
        )
        with pytest.raises(ValueError, match="cannot be deleted"):
            log.delete()


@pytest.mark.django_db
class TestSystemSetting:
    """Tests for SystemSetting model."""

    def test_get_value_returns_default_when_not_found(self):
        """Test get_value returns default when setting doesn't exist."""
        result = SystemSetting.get_value("nonexistent", default="default_value")
        assert result == "default_value"

    def test_set_and_get_value(self):
        """Test setting and getting a value."""
        SystemSetting.set_value("test_key", {"nested": "value"})
        result = SystemSetting.get_value("test_key")
        assert result == {"nested": "value"}

    def test_set_value_updates_existing(self):
        """Test that set_value updates existing settings."""
        SystemSetting.set_value("test_key", "first")
        SystemSetting.set_value("test_key", "second")
        assert SystemSetting.objects.filter(key="test_key").count() == 1
        assert SystemSetting.get_value("test_key") == "second"
