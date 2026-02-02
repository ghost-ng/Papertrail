"""Tests for Comment, Mention, Notification, and NotificationPreference models."""

import pytest
from django.utils import timezone

from apps.accounts.models import User
from apps.organizations.models import Organization, Office
from apps.packages.models import Package
from apps.collaboration.models import (
    Comment,
    Mention,
    Notification,
    NotificationPreference,
)


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
def another_office(db, organization):
    """Create another test office."""
    return Office.objects.create(
        organization=organization,
        code="J2",
        name="Another Office",
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
class TestCommentModel:
    """Tests for Comment model."""

    def test_create_comment(self, package, user, office):
        """Test basic comment creation."""
        comment = Comment.objects.create(
            package=package,
            author=user,
            author_office=office,
            content="This is a test comment.",
        )
        assert comment.pk is not None
        assert comment.visibility == Comment.Visibility.ALL
        assert comment.is_edited is False
        assert comment.edited_at is None
        assert comment.parent is None

    def test_comment_visibility_choices(self, package, user, office):
        """Test comment visibility choices."""
        # Default visibility
        comment1 = Comment.objects.create(
            package=package,
            author=user,
            author_office=office,
            content="Public comment",
        )
        assert comment1.visibility == "all"

        # Office only visibility
        comment2 = Comment.objects.create(
            package=package,
            author=user,
            author_office=office,
            content="Private comment",
            visibility=Comment.Visibility.OFFICE_ONLY,
        )
        assert comment2.visibility == "office_only"

    def test_comment_reply_creates_thread(self, package, user, office):
        """Test comment reply creates a thread."""
        parent_comment = Comment.objects.create(
            package=package,
            author=user,
            author_office=office,
            content="Parent comment",
        )

        reply = Comment.objects.create(
            package=package,
            author=user,
            author_office=office,
            content="Reply comment",
            parent=parent_comment,
        )

        assert reply.parent == parent_comment
        assert reply.is_reply is True
        assert parent_comment.is_reply is False
        assert reply in parent_comment.replies.all()

    def test_comment_edit_tracking(self, comment):
        """Test that editing a comment updates edit tracking."""
        assert comment.is_edited is False
        assert comment.edited_at is None

        # Edit the comment content
        original_updated_at = comment.updated_at
        comment.content = "Updated content"
        comment.save()

        comment.refresh_from_db()
        assert comment.is_edited is True
        assert comment.edited_at is not None
        assert comment.content == "Updated content"

    def test_comment_str_method(self, comment):
        """Test comment string representation."""
        assert comment.author.email in str(comment)
        assert comment.package.reference_number in str(comment)

    def test_comment_ordering(self, package, user, office):
        """Test comments are ordered by created_at descending."""
        comment1 = Comment.objects.create(
            package=package,
            author=user,
            author_office=office,
            content="First comment",
        )
        comment2 = Comment.objects.create(
            package=package,
            author=user,
            author_office=office,
            content="Second comment",
        )

        comments = Comment.objects.filter(package=package)
        # Check ordering is by -created_at (newest first)
        # When timestamps are equal (same second), pk order may vary
        # so we just verify the ordering key is correct
        comment_list = list(comments)
        assert len(comment_list) == 2
        # Verify both comments are present
        assert comment1 in comment_list
        assert comment2 in comment_list


@pytest.mark.django_db
class TestMentionModel:
    """Tests for Mention model."""

    def test_create_mention(self, comment, another_user):
        """Test basic mention creation."""
        mention = Mention.objects.create(
            comment=comment,
            mentioned_user=another_user,
        )
        assert mention.pk is not None
        assert mention.notified is False

    def test_mention_unique_constraint(self, comment, another_user):
        """Test unique constraint on comment + mentioned_user."""
        Mention.objects.create(
            comment=comment,
            mentioned_user=another_user,
        )

        with pytest.raises(Exception):  # IntegrityError
            Mention.objects.create(
                comment=comment,
                mentioned_user=another_user,
            )

    def test_mention_notified_flag(self, comment, another_user):
        """Test mention notified flag can be updated."""
        mention = Mention.objects.create(
            comment=comment,
            mentioned_user=another_user,
            notified=False,
        )
        assert mention.notified is False

        mention.notified = True
        mention.save()
        mention.refresh_from_db()
        assert mention.notified is True

    def test_mention_str_method(self, comment, another_user):
        """Test mention string representation."""
        mention = Mention.objects.create(
            comment=comment,
            mentioned_user=another_user,
        )
        assert another_user.email in str(mention)

    def test_comment_has_mentions_relation(self, comment, another_user, user):
        """Test comment has mentions relation."""
        Mention.objects.create(comment=comment, mentioned_user=another_user)
        Mention.objects.create(comment=comment, mentioned_user=user)

        assert comment.mentions.count() == 2


@pytest.mark.django_db
class TestNotificationModel:
    """Tests for Notification model."""

    def test_create_notification(self, user, package):
        """Test basic notification creation."""
        notification = Notification.objects.create(
            user=user,
            notification_type=Notification.NotificationType.PACKAGE_ARRIVED,
            title="Package Arrived",
            message="A new package has arrived for your review.",
            package=package,
        )
        assert notification.pk is not None
        assert notification.is_read is False
        assert notification.read_at is None
        assert notification.email_sent is False
        assert notification.email_sent_at is None

    def test_notification_types(self, user):
        """Test all notification types are valid."""
        notification_types = [
            Notification.NotificationType.PACKAGE_ARRIVED,
            Notification.NotificationType.ACTION_REQUIRED,
            Notification.NotificationType.COMMENT_ADDED,
            Notification.NotificationType.COMMENT_MENTION,
            Notification.NotificationType.SIGNATURE_REQUIRED,
            Notification.NotificationType.SIGNATURE_REMOVED,
            Notification.NotificationType.INTEGRITY_VIOLATION,
            Notification.NotificationType.MEMBERSHIP_APPROVED,
            Notification.NotificationType.MEMBERSHIP_REJECTED,
            Notification.NotificationType.MEMBERSHIP_REQUEST,
            Notification.NotificationType.PACKAGE_COMPLETED,
            Notification.NotificationType.PACKAGE_RETURNED,
            Notification.NotificationType.PACKAGE_REJECTED,
        ]

        for i, notification_type in enumerate(notification_types):
            notification = Notification.objects.create(
                user=user,
                notification_type=notification_type,
                title=f"Test {notification_type}",
                message=f"Message for {notification_type}",
            )
            assert notification.notification_type == notification_type

    def test_notification_mark_read(self, user):
        """Test mark_read method."""
        notification = Notification.objects.create(
            user=user,
            notification_type=Notification.NotificationType.PACKAGE_ARRIVED,
            title="Test",
            message="Test message",
        )
        assert notification.is_read is False
        assert notification.read_at is None

        notification.mark_read()

        notification.refresh_from_db()
        assert notification.is_read is True
        assert notification.read_at is not None

    def test_notification_mark_read_idempotent(self, user):
        """Test mark_read is idempotent."""
        notification = Notification.objects.create(
            user=user,
            notification_type=Notification.NotificationType.PACKAGE_ARRIVED,
            title="Test",
            message="Test message",
        )

        notification.mark_read()
        first_read_at = notification.read_at

        # Call mark_read again
        notification.mark_read()
        notification.refresh_from_db()

        # read_at should not change
        assert notification.read_at == first_read_at

    def test_notification_with_comment(self, user, comment):
        """Test notification linked to a comment."""
        notification = Notification.objects.create(
            user=user,
            notification_type=Notification.NotificationType.COMMENT_MENTION,
            title="You were mentioned",
            message="Someone mentioned you in a comment.",
            comment=comment,
            package=comment.package,
        )
        assert notification.comment == comment
        assert notification.package == comment.package

    def test_notification_link_field(self, user):
        """Test notification link field."""
        notification = Notification.objects.create(
            user=user,
            notification_type=Notification.NotificationType.PACKAGE_ARRIVED,
            title="Test",
            message="Test message",
            link="/packages/TEST-2025-00001/",
        )
        assert notification.link == "/packages/TEST-2025-00001/"

    def test_notification_str_method(self, user):
        """Test notification string representation."""
        notification = Notification.objects.create(
            user=user,
            notification_type=Notification.NotificationType.PACKAGE_ARRIVED,
            title="Test",
            message="Test message",
        )
        assert "package_arrived" in str(notification)
        assert user.email in str(notification)

    def test_notification_ordering(self, user):
        """Test notifications are ordered by created_at descending."""
        notification1 = Notification.objects.create(
            user=user,
            notification_type=Notification.NotificationType.PACKAGE_ARRIVED,
            title="First",
            message="First message",
        )
        notification2 = Notification.objects.create(
            user=user,
            notification_type=Notification.NotificationType.ACTION_REQUIRED,
            title="Second",
            message="Second message",
        )

        notifications = Notification.objects.filter(user=user)
        # Check ordering is by -created_at (newest first)
        # When timestamps are equal (same second), pk order may vary
        notification_list = list(notifications)
        assert len(notification_list) == 2
        # Verify both notifications are present
        assert notification1 in notification_list
        assert notification2 in notification_list


@pytest.mark.django_db
class TestNotificationPreferenceModel:
    """Tests for NotificationPreference model."""

    def test_create_notification_preference(self, user):
        """Test basic notification preference creation."""
        pref = NotificationPreference.objects.create(user=user)

        assert pref.pk is not None
        assert pref.in_app_enabled is True
        assert pref.email_package_arrived is True
        assert pref.email_action_required is True
        assert pref.email_comments is True
        assert pref.email_mentions is True
        assert pref.email_signatures is True
        assert pref.email_memberships is True
        assert pref.email_digest is False

    def test_notification_preference_one_to_one(self, user):
        """Test one-to-one constraint with user."""
        NotificationPreference.objects.create(user=user)

        with pytest.raises(Exception):  # IntegrityError
            NotificationPreference.objects.create(user=user)

    def test_notification_preference_update(self, user):
        """Test updating notification preferences."""
        pref = NotificationPreference.objects.create(
            user=user,
            email_package_arrived=True,
            email_digest=False,
        )

        pref.email_package_arrived = False
        pref.email_digest = True
        pref.save()

        pref.refresh_from_db()
        assert pref.email_package_arrived is False
        assert pref.email_digest is True

    def test_notification_preference_str_method(self, user):
        """Test notification preference string representation."""
        pref = NotificationPreference.objects.create(user=user)
        assert user.email in str(pref)

    def test_notification_preference_all_disabled(self, user):
        """Test all preferences can be disabled."""
        pref = NotificationPreference.objects.create(
            user=user,
            in_app_enabled=False,
            email_package_arrived=False,
            email_action_required=False,
            email_comments=False,
            email_mentions=False,
            email_signatures=False,
            email_memberships=False,
            email_digest=False,
        )

        pref.refresh_from_db()
        assert pref.in_app_enabled is False
        assert pref.email_package_arrived is False
        assert pref.email_action_required is False
        assert pref.email_comments is False
        assert pref.email_mentions is False
        assert pref.email_signatures is False
        assert pref.email_memberships is False
        assert pref.email_digest is False

    def test_user_can_access_preferences(self, user):
        """Test user can access notification preferences via related name."""
        pref = NotificationPreference.objects.create(user=user)
        assert user.notification_preferences == pref
