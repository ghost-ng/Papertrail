"""Services for collaboration app."""

import re
from typing import TYPE_CHECKING

from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.collaboration.models import (
    Comment,
    Mention,
    Notification,
    NotificationPreference,
)
from apps.organizations.models import OfficeMembership

if TYPE_CHECKING:
    from apps.organizations.models import Office

User = get_user_model()


class NotificationService:
    """Service for creating and managing notifications."""

    @classmethod
    def notify(
        cls,
        user,
        notification_type: str,
        title: str,
        message: str,
        link: str = "",
        package=None,
        comment=None,
        send_email: bool = True,
    ) -> Notification:
        """
        Create a notification for a user, optionally send email.

        Args:
            user: The user to notify.
            notification_type: Type of notification (from Notification.NotificationType).
            title: Title of the notification.
            message: Message body of the notification.
            link: Optional link to relevant resource.
            package: Optional related package.
            comment: Optional related comment.
            send_email: Whether to attempt sending an email (default True).

        Returns:
            The created Notification instance.
        """
        notification = Notification.objects.create(
            user=user,
            notification_type=notification_type,
            title=title,
            message=message,
            link=link,
            package=package,
            comment=comment,
        )

        if send_email:
            cls._maybe_send_email(notification)

        return notification

    @classmethod
    def notify_office(
        cls,
        office: "Office",
        notification_type: str,
        title: str,
        message: str,
        link: str = "",
        package=None,
        exclude_user=None,
    ) -> list[Notification]:
        """
        Notify all members of an office.

        Args:
            office: The office whose members should be notified.
            notification_type: Type of notification.
            title: Title of the notification.
            message: Message body of the notification.
            link: Optional link to relevant resource.
            package: Optional related package.
            exclude_user: Optional user to exclude from notifications.

        Returns:
            List of created Notification instances.
        """
        # Get all memberships for this office (membership is immediate)
        memberships = OfficeMembership.objects.filter(
            office=office,
        ).select_related("user")

        notifications = []
        for membership in memberships:
            # Skip excluded user
            if exclude_user and membership.user == exclude_user:
                continue

            notification = cls.notify(
                user=membership.user,
                notification_type=notification_type,
                title=title,
                message=message,
                link=link,
                package=package,
            )
            notifications.append(notification)

        return notifications

    @classmethod
    def mark_read(cls, user, notification_ids: list) -> int:
        """
        Mark specific notifications as read for a user.

        Args:
            user: The user whose notifications should be marked.
            notification_ids: List of notification IDs to mark as read.

        Returns:
            Count of notifications updated.
        """
        now = timezone.now()
        return Notification.objects.filter(
            user=user,
            id__in=notification_ids,
            is_read=False,
        ).update(is_read=True, read_at=now)

    @classmethod
    def mark_all_read(cls, user) -> int:
        """
        Mark all notifications as read for a user.

        Args:
            user: The user whose notifications should be marked.

        Returns:
            Count of notifications updated.
        """
        now = timezone.now()
        return Notification.objects.filter(
            user=user,
            is_read=False,
        ).update(is_read=True, read_at=now)

    @classmethod
    def get_unread_count(cls, user) -> int:
        """
        Get count of unread notifications for a user.

        Args:
            user: The user to check.

        Returns:
            Count of unread notifications.
        """
        return Notification.objects.filter(
            user=user,
            is_read=False,
        ).count()

    @classmethod
    def _maybe_send_email(cls, notification: Notification) -> bool:
        """
        Send email if user preferences allow it.

        Args:
            notification: The notification to potentially send email for.

        Returns:
            True if email was sent, False otherwise.
        """
        # Get or create user preferences
        try:
            prefs = notification.user.notification_preferences
        except NotificationPreference.DoesNotExist:
            # If no preferences exist, use defaults (all enabled)
            prefs = NotificationPreference(user=notification.user)

        if not cls._should_email(notification, prefs):
            return False

        # Send the email
        try:
            send_mail(
                subject=notification.title,
                message=notification.message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[notification.user.email],
                fail_silently=True,
            )
            # Mark email as sent
            notification.email_sent = True
            notification.email_sent_at = timezone.now()
            notification.save(update_fields=["email_sent", "email_sent_at"])
            return True
        except Exception:
            return False

    @classmethod
    def _should_email(cls, notification: Notification, prefs: NotificationPreference) -> bool:
        """
        Determine if notification should trigger email based on type and prefs.

        Args:
            notification: The notification to check.
            prefs: User's notification preferences.

        Returns:
            True if email should be sent, False otherwise.
        """
        notification_type = notification.notification_type

        # Map notification types to preference fields
        type_to_pref = {
            Notification.NotificationType.PACKAGE_ARRIVED: prefs.email_package_arrived,
            Notification.NotificationType.ACTION_REQUIRED: prefs.email_action_required,
            Notification.NotificationType.COMMENT_ADDED: prefs.email_comments,
            Notification.NotificationType.COMMENT_MENTION: prefs.email_mentions,
            Notification.NotificationType.SIGNATURE_REQUIRED: prefs.email_signatures,
            Notification.NotificationType.SIGNATURE_REMOVED: prefs.email_signatures,
            Notification.NotificationType.INTEGRITY_VIOLATION: prefs.email_action_required,
            Notification.NotificationType.MEMBERSHIP_APPROVED: prefs.email_memberships,
            Notification.NotificationType.MEMBERSHIP_REJECTED: prefs.email_memberships,
            Notification.NotificationType.MEMBERSHIP_REQUEST: prefs.email_memberships,
            Notification.NotificationType.PACKAGE_COMPLETED: prefs.email_package_arrived,
            Notification.NotificationType.PACKAGE_RETURNED: prefs.email_package_arrived,
            Notification.NotificationType.PACKAGE_REJECTED: prefs.email_package_arrived,
        }

        return type_to_pref.get(notification_type, True)


class MentionService:
    """Service for parsing and processing @mentions in comments."""

    # Pattern to match @email@domain.com format
    # Uses word characters plus dots and hyphens for the email parts
    # Stops at common punctuation (comma, period at end, etc.)
    MENTION_PATTERN = re.compile(r"@([\w.+-]+@[\w.-]+\.[a-zA-Z]{2,})")

    @classmethod
    def parse_mentions(cls, content: str) -> list[str]:
        """
        Extract email addresses from @mentions in content.

        Args:
            content: The text content to parse for mentions.

        Returns:
            List of email addresses found in the content.
        """
        if not content:
            return []

        matches = cls.MENTION_PATTERN.findall(content)
        # Return unique emails while preserving order
        seen = set()
        unique_emails = []
        for email in matches:
            email_lower = email.lower()
            if email_lower not in seen:
                seen.add(email_lower)
                unique_emails.append(email)
        return unique_emails

    @classmethod
    @transaction.atomic
    def process_comment_mentions(cls, comment: Comment) -> list[Mention]:
        """
        Parse comment for mentions and create Mention records + notifications.

        Args:
            comment: The comment to process for mentions.

        Returns:
            List of created Mention instances.
        """
        emails = cls.parse_mentions(comment.content)

        if not emails:
            return []

        # Get users by email (case-insensitive)
        users = User.objects.filter(email__in=emails)
        email_to_user = {user.email.lower(): user for user in users}

        mentions = []
        for email in emails:
            user = email_to_user.get(email.lower())
            if not user:
                # User not found, skip
                continue

            # Don't mention yourself
            if user == comment.author:
                continue

            # Create mention record
            mention, created = Mention.objects.get_or_create(
                comment=comment,
                mentioned_user=user,
            )

            if created:
                mentions.append(mention)

                # Create notification for the mentioned user
                NotificationService.notify(
                    user=user,
                    notification_type=Notification.NotificationType.COMMENT_MENTION,
                    title="You were mentioned in a comment",
                    message=f"{comment.author.email} mentioned you in a comment on {comment.package.reference_number}",
                    link=f"/packages/{comment.package.reference_number}/",
                    package=comment.package,
                    comment=comment,
                )

                # Mark mention as notified
                mention.notified = True
                mention.save(update_fields=["notified"])

        return mentions
