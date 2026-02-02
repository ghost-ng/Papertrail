"""Tests for NotificationService and MentionService."""

import pytest
from unittest.mock import patch, MagicMock

from apps.accounts.models import User
from apps.organizations.models import Organization, Office, OfficeMembership
from apps.packages.models import Package
from apps.collaboration.models import (
    Comment,
    Mention,
    Notification,
    NotificationPreference,
)
from apps.collaboration.services import NotificationService, MentionService


@pytest.fixture
def user(db):
    """Create a test user."""
    return User.objects.create_user(
        email="test@example.com",
        password="testpass123",
        first_name="Test",
        last_name="User",
    )


@pytest.fixture
def another_user(db):
    """Create another test user."""
    return User.objects.create_user(
        email="another@example.com",
        password="testpass123",
        first_name="Another",
        last_name="User",
    )


@pytest.fixture
def third_user(db):
    """Create a third test user."""
    return User.objects.create_user(
        email="third@example.com",
        password="testpass123",
        first_name="Third",
        last_name="User",
    )


@pytest.fixture
def organization(db):
    """Create a test organization."""
    return Organization.objects.create(code="TEST", name="Test Organization")


@pytest.fixture
def office(db, organization):
    """Create a test office."""
    return Office.objects.create(
        organization=organization,
        code="J1",
        name="Test Office",
    )


@pytest.fixture
def package(db, user, organization, office):
    """Create a test package."""
    return Package.objects.create(
        organization=organization,
        title="Test Package",
        originator=user,
        originating_office=office,
    )


@pytest.fixture
def comment(db, package, user, office):
    """Create a test comment."""
    return Comment.objects.create(
        package=package,
        author=user,
        author_office=office,
        content="Test comment content",
    )


@pytest.mark.django_db
class TestNotificationService:
    """Tests for NotificationService."""

    def test_notify_creates_notification(self, user, package):
        """Test that notify creates a notification for a user."""
        notification = NotificationService.notify(
            user=user,
            notification_type=Notification.NotificationType.PACKAGE_ARRIVED,
            title="Package Arrived",
            message="A new package has arrived.",
            link="/packages/TEST-2025-00001/",
            package=package,
            send_email=False,
        )

        assert notification is not None
        assert notification.pk is not None
        assert notification.user == user
        assert notification.notification_type == Notification.NotificationType.PACKAGE_ARRIVED
        assert notification.title == "Package Arrived"
        assert notification.message == "A new package has arrived."
        assert notification.link == "/packages/TEST-2025-00001/"
        assert notification.package == package
        assert notification.is_read is False

    def test_notify_creates_notification_with_comment(self, user, comment):
        """Test notification creation with a related comment."""
        notification = NotificationService.notify(
            user=user,
            notification_type=Notification.NotificationType.COMMENT_MENTION,
            title="You were mentioned",
            message="Someone mentioned you.",
            comment=comment,
            package=comment.package,
            send_email=False,
        )

        assert notification.comment == comment
        assert notification.package == comment.package

    @patch("apps.collaboration.services.send_mail")
    def test_notify_sends_email_when_prefs_allow(self, mock_send_mail, user):
        """Test that email is sent when preferences allow."""
        # Create preferences allowing email
        NotificationPreference.objects.create(
            user=user,
            email_package_arrived=True,
        )

        notification = NotificationService.notify(
            user=user,
            notification_type=Notification.NotificationType.PACKAGE_ARRIVED,
            title="Package Arrived",
            message="A new package has arrived.",
            send_email=True,
        )

        mock_send_mail.assert_called_once()
        notification.refresh_from_db()
        assert notification.email_sent is True
        assert notification.email_sent_at is not None

    @patch("apps.collaboration.services.send_mail")
    def test_notify_skips_email_when_prefs_disabled(self, mock_send_mail, user):
        """Test that email is not sent when preferences disable it."""
        # Create preferences disabling email for package arrived
        NotificationPreference.objects.create(
            user=user,
            email_package_arrived=False,
        )

        notification = NotificationService.notify(
            user=user,
            notification_type=Notification.NotificationType.PACKAGE_ARRIVED,
            title="Package Arrived",
            message="A new package has arrived.",
            send_email=True,
        )

        mock_send_mail.assert_not_called()
        notification.refresh_from_db()
        assert notification.email_sent is False

    def test_notify_office(self, office, user, another_user, package):
        """Test notifying all members of an office."""
        # Create memberships (membership is immediate, no status)
        OfficeMembership.objects.create(
            user=user,
            office=office,
        )
        OfficeMembership.objects.create(
            user=another_user,
            office=office,
        )

        notifications = NotificationService.notify_office(
            office=office,
            notification_type=Notification.NotificationType.PACKAGE_ARRIVED,
            title="Package Arrived",
            message="A new package has arrived.",
            package=package,
        )

        assert len(notifications) == 2
        notified_users = {n.user for n in notifications}
        assert user in notified_users
        assert another_user in notified_users

    def test_notify_office_excludes_user(self, office, user, another_user, package):
        """Test that exclude_user is excluded from notifications."""
        # Create memberships (membership is immediate, no status)
        OfficeMembership.objects.create(
            user=user,
            office=office,
        )
        OfficeMembership.objects.create(
            user=another_user,
            office=office,
        )

        notifications = NotificationService.notify_office(
            office=office,
            notification_type=Notification.NotificationType.PACKAGE_ARRIVED,
            title="Package Arrived",
            message="A new package has arrived.",
            package=package,
            exclude_user=user,
        )

        assert len(notifications) == 1
        assert notifications[0].user == another_user

    def test_mark_read(self, user):
        """Test marking specific notifications as read."""
        # Create multiple notifications
        n1 = Notification.objects.create(
            user=user,
            notification_type=Notification.NotificationType.PACKAGE_ARRIVED,
            title="Notification 1",
            message="Message 1",
        )
        n2 = Notification.objects.create(
            user=user,
            notification_type=Notification.NotificationType.PACKAGE_ARRIVED,
            title="Notification 2",
            message="Message 2",
        )
        n3 = Notification.objects.create(
            user=user,
            notification_type=Notification.NotificationType.PACKAGE_ARRIVED,
            title="Notification 3",
            message="Message 3",
        )

        # Mark only first two as read
        count = NotificationService.mark_read(user, [n1.id, n2.id])

        assert count == 2

        n1.refresh_from_db()
        n2.refresh_from_db()
        n3.refresh_from_db()

        assert n1.is_read is True
        assert n1.read_at is not None
        assert n2.is_read is True
        assert n2.read_at is not None
        assert n3.is_read is False
        assert n3.read_at is None

    def test_mark_read_only_affects_users_notifications(self, user, another_user):
        """Test that mark_read only affects the specified user's notifications."""
        n1 = Notification.objects.create(
            user=user,
            notification_type=Notification.NotificationType.PACKAGE_ARRIVED,
            title="User's Notification",
            message="Message",
        )
        n2 = Notification.objects.create(
            user=another_user,
            notification_type=Notification.NotificationType.PACKAGE_ARRIVED,
            title="Another User's Notification",
            message="Message",
        )

        # Try to mark both as read for user
        count = NotificationService.mark_read(user, [n1.id, n2.id])

        # Should only update user's notification
        assert count == 1

        n1.refresh_from_db()
        n2.refresh_from_db()

        assert n1.is_read is True
        assert n2.is_read is False

    def test_mark_all_read(self, user):
        """Test marking all notifications as read."""
        # Create multiple notifications
        for i in range(5):
            Notification.objects.create(
                user=user,
                notification_type=Notification.NotificationType.PACKAGE_ARRIVED,
                title=f"Notification {i}",
                message=f"Message {i}",
            )

        count = NotificationService.mark_all_read(user)

        assert count == 5

        unread_count = Notification.objects.filter(user=user, is_read=False).count()
        assert unread_count == 0

    def test_mark_all_read_only_affects_unread(self, user):
        """Test that mark_all_read only updates unread notifications."""
        # Create some read and some unread notifications
        n1 = Notification.objects.create(
            user=user,
            notification_type=Notification.NotificationType.PACKAGE_ARRIVED,
            title="Already Read",
            message="Message",
            is_read=True,
        )
        n2 = Notification.objects.create(
            user=user,
            notification_type=Notification.NotificationType.PACKAGE_ARRIVED,
            title="Unread",
            message="Message",
        )

        count = NotificationService.mark_all_read(user)

        # Should only update the unread notification
        assert count == 1

    def test_get_unread_count(self, user):
        """Test getting unread notification count."""
        # Create mix of read and unread
        Notification.objects.create(
            user=user,
            notification_type=Notification.NotificationType.PACKAGE_ARRIVED,
            title="Read 1",
            message="Message",
            is_read=True,
        )
        Notification.objects.create(
            user=user,
            notification_type=Notification.NotificationType.PACKAGE_ARRIVED,
            title="Unread 1",
            message="Message",
        )
        Notification.objects.create(
            user=user,
            notification_type=Notification.NotificationType.PACKAGE_ARRIVED,
            title="Unread 2",
            message="Message",
        )

        count = NotificationService.get_unread_count(user)

        assert count == 2

    def test_get_unread_count_zero_when_all_read(self, user):
        """Test unread count is zero when all are read."""
        Notification.objects.create(
            user=user,
            notification_type=Notification.NotificationType.PACKAGE_ARRIVED,
            title="Read",
            message="Message",
            is_read=True,
        )

        count = NotificationService.get_unread_count(user)

        assert count == 0


@pytest.mark.django_db
class TestMentionService:
    """Tests for MentionService."""

    def test_parse_mentions(self):
        """Test parsing @mentions from content."""
        content = "Hey @john@example.com, please review this. cc @jane@company.org"
        emails = MentionService.parse_mentions(content)

        assert len(emails) == 2
        assert "john@example.com" in emails
        assert "jane@company.org" in emails

    def test_parse_mentions_single(self):
        """Test parsing a single mention."""
        content = "Hello @user@test.com"
        emails = MentionService.parse_mentions(content)

        assert len(emails) == 1
        assert "user@test.com" in emails

    def test_parse_mentions_no_matches(self):
        """Test parsing content with no mentions."""
        content = "This is a comment without any mentions."
        emails = MentionService.parse_mentions(content)

        assert len(emails) == 0

    def test_parse_mentions_empty_content(self):
        """Test parsing empty content."""
        emails = MentionService.parse_mentions("")
        assert len(emails) == 0

        emails = MentionService.parse_mentions(None)
        assert len(emails) == 0

    def test_parse_mentions_deduplicates(self):
        """Test that duplicate mentions are deduplicated."""
        content = "Hey @user@test.com and @user@test.com again"
        emails = MentionService.parse_mentions(content)

        assert len(emails) == 1
        assert "user@test.com" in emails

    def test_parse_mentions_preserves_order(self):
        """Test that mentions are returned in order of appearance."""
        content = "@first@example.com @second@example.com @third@example.com"
        emails = MentionService.parse_mentions(content)

        assert len(emails) == 3
        assert emails[0] == "first@example.com"
        assert emails[1] == "second@example.com"
        assert emails[2] == "third@example.com"

    def test_process_comment_mentions(self, package, user, another_user, office):
        """Test processing mentions in a comment."""
        comment = Comment.objects.create(
            package=package,
            author=user,
            author_office=office,
            content=f"Hey @{another_user.email}, please check this.",
        )

        mentions = MentionService.process_comment_mentions(comment)

        assert len(mentions) == 1
        assert mentions[0].mentioned_user == another_user
        assert mentions[0].comment == comment
        assert mentions[0].notified is True

        # Check notification was created
        notification = Notification.objects.filter(
            user=another_user,
            notification_type=Notification.NotificationType.COMMENT_MENTION,
            comment=comment,
        ).first()

        assert notification is not None
        assert "mentioned" in notification.title

    def test_process_comment_mentions_skip_self(self, package, user, office):
        """Test that self-mentions are skipped."""
        comment = Comment.objects.create(
            package=package,
            author=user,
            author_office=office,
            content=f"Note to self: @{user.email}",
        )

        mentions = MentionService.process_comment_mentions(comment)

        assert len(mentions) == 0

        # No mention record should exist
        assert Mention.objects.filter(comment=comment).count() == 0

    def test_process_comment_mentions_skip_nonexistent_users(
        self, package, user, office
    ):
        """Test that mentions of nonexistent users are skipped."""
        comment = Comment.objects.create(
            package=package,
            author=user,
            author_office=office,
            content="Hey @nonexistent@example.com, are you there?",
        )

        mentions = MentionService.process_comment_mentions(comment)

        assert len(mentions) == 0

    def test_process_comment_mentions_multiple_users(
        self, package, user, another_user, third_user, office
    ):
        """Test processing multiple mentions in a comment."""
        comment = Comment.objects.create(
            package=package,
            author=user,
            author_office=office,
            content=f"Hey @{another_user.email} and @{third_user.email}, please review.",
        )

        mentions = MentionService.process_comment_mentions(comment)

        assert len(mentions) == 2

        mentioned_users = {m.mentioned_user for m in mentions}
        assert another_user in mentioned_users
        assert third_user in mentioned_users

        # Check notifications were created for both
        notifications = Notification.objects.filter(
            notification_type=Notification.NotificationType.COMMENT_MENTION,
            comment=comment,
        )
        assert notifications.count() == 2

    def test_process_comment_mentions_idempotent(
        self, package, user, another_user, office
    ):
        """Test that processing mentions twice doesn't create duplicates."""
        comment = Comment.objects.create(
            package=package,
            author=user,
            author_office=office,
            content=f"Hey @{another_user.email}, please check this.",
        )

        # Process twice
        mentions1 = MentionService.process_comment_mentions(comment)
        mentions2 = MentionService.process_comment_mentions(comment)

        # First call should create mention
        assert len(mentions1) == 1

        # Second call should not create duplicate
        assert len(mentions2) == 0

        # Only one mention should exist
        assert Mention.objects.filter(comment=comment).count() == 1

    def test_process_comment_mentions_no_mentions(self, package, user, office):
        """Test processing a comment with no mentions."""
        comment = Comment.objects.create(
            package=package,
            author=user,
            author_office=office,
            content="This comment has no mentions.",
        )

        mentions = MentionService.process_comment_mentions(comment)

        assert len(mentions) == 0
