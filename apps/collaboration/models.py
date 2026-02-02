"""Collaboration models for comments, mentions, and notifications."""

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.models import TimeStampedModel


class Comment(TimeStampedModel):
    """Comment on a package with threading support."""

    class Visibility(models.TextChoices):
        ALL = "all", "All Users"
        OFFICE_ONLY = "office_only", "Office Only"

    package = models.ForeignKey(
        "packages.Package",
        on_delete=models.CASCADE,
        related_name="comments",
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="comments",
    )
    author_office = models.ForeignKey(
        "organizations.Office",
        on_delete=models.CASCADE,
        related_name="comments",
    )
    parent = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="replies",
    )
    content = models.TextField()
    visibility = models.CharField(
        max_length=20,
        choices=Visibility.choices,
        default=Visibility.ALL,
    )
    is_edited = models.BooleanField(default=False)
    edited_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["package", "-created_at"]),
            models.Index(fields=["author"]),
            models.Index(fields=["parent"]),
        ]

    def __str__(self):
        return f"Comment by {self.author.email} on {self.package.reference_number}"

    @property
    def is_reply(self):
        """Check if this comment is a reply to another comment."""
        return self.parent is not None

    def save(self, *args, **kwargs):
        """Track edit timestamp when content is modified."""
        if self.pk:
            # Check if content was modified
            try:
                original = Comment.objects.get(pk=self.pk)
                if original.content != self.content:
                    self.is_edited = True
                    self.edited_at = timezone.now()
            except Comment.DoesNotExist:
                pass
        super().save(*args, **kwargs)


class Mention(TimeStampedModel):
    """User mention within a comment."""

    comment = models.ForeignKey(
        Comment,
        on_delete=models.CASCADE,
        related_name="mentions",
    )
    mentioned_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="mentions",
    )
    notified = models.BooleanField(default=False)

    class Meta:
        unique_together = ["comment", "mentioned_user"]
        indexes = [
            models.Index(fields=["mentioned_user", "notified"]),
        ]

    def __str__(self):
        return f"@{self.mentioned_user.email} in comment {self.comment.pk}"


class Notification(TimeStampedModel):
    """User notification for various system events."""

    class NotificationType(models.TextChoices):
        PACKAGE_ARRIVED = "package_arrived", "Package Arrived"
        ACTION_REQUIRED = "action_required", "Action Required"
        COMMENT_ADDED = "comment_added", "Comment Added"
        COMMENT_MENTION = "comment_mention", "Comment Mention"
        SIGNATURE_REQUIRED = "signature_required", "Signature Required"
        SIGNATURE_REMOVED = "signature_removed", "Signature Removed"
        INTEGRITY_VIOLATION = "integrity_violation", "Integrity Violation"
        MEMBERSHIP_APPROVED = "membership_approved", "Membership Approved"
        MEMBERSHIP_REJECTED = "membership_rejected", "Membership Rejected"
        MEMBERSHIP_REQUEST = "membership_request", "Membership Request"
        PACKAGE_COMPLETED = "package_completed", "Package Completed"
        PACKAGE_RETURNED = "package_returned", "Package Returned"
        PACKAGE_REJECTED = "package_rejected", "Package Rejected"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    notification_type = models.CharField(
        max_length=30,
        choices=NotificationType.choices,
    )
    title = models.CharField(max_length=200)
    message = models.TextField()
    link = models.CharField(max_length=500, blank=True)
    package = models.ForeignKey(
        "packages.Package",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="notifications",
    )
    comment = models.ForeignKey(
        Comment,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="notifications",
    )
    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)
    email_sent = models.BooleanField(default=False)
    email_sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "-created_at"]),
            models.Index(fields=["user", "is_read"]),
            models.Index(fields=["notification_type"]),
        ]

    def __str__(self):
        return f"{self.notification_type} notification for {self.user.email}"

    def mark_read(self):
        """Mark the notification as read."""
        if not self.is_read:
            self.is_read = True
            self.read_at = timezone.now()
            self.save(update_fields=["is_read", "read_at", "updated_at"])


class NotificationPreference(TimeStampedModel):
    """User notification preferences."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notification_preferences",
    )
    in_app_enabled = models.BooleanField(default=True)
    email_package_arrived = models.BooleanField(default=True)
    email_action_required = models.BooleanField(default=True)
    email_comments = models.BooleanField(default=True)
    email_mentions = models.BooleanField(default=True)
    email_signatures = models.BooleanField(default=True)
    email_memberships = models.BooleanField(default=True)
    email_digest = models.BooleanField(default=False)

    class Meta:
        verbose_name = "Notification Preference"
        verbose_name_plural = "Notification Preferences"

    def __str__(self):
        return f"Notification preferences for {self.user.email}"
