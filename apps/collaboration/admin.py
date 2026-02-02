"""Admin configuration for collaboration app."""

from django.contrib import admin
from django.utils.html import format_html

from apps.collaboration.models import (
    Comment,
    Mention,
    Notification,
    NotificationPreference,
)


class MentionInline(admin.TabularInline):
    """Inline admin for mentions within a comment."""

    model = Mention
    extra = 0
    readonly_fields = ["created_at"]
    fields = ["mentioned_user", "notified", "created_at"]


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    """Admin for Comment model."""

    list_display = [
        "id",
        "package_link",
        "author",
        "author_office",
        "visibility_badge",
        "is_reply",
        "is_edited",
        "created_at",
    ]
    list_filter = ["visibility", "is_edited", "created_at", "author_office"]
    search_fields = [
        "content",
        "author__email",
        "package__reference_number",
    ]
    readonly_fields = ["created_at", "updated_at", "is_edited", "edited_at"]
    raw_id_fields = ["package", "author", "author_office", "parent"]
    inlines = [MentionInline]
    date_hierarchy = "created_at"

    fieldsets = [
        (None, {"fields": ["package", "author", "author_office"]}),
        ("Content", {"fields": ["content", "visibility"]}),
        ("Threading", {"fields": ["parent"]}),
        (
            "Edit History",
            {
                "fields": ["is_edited", "edited_at"],
                "classes": ["collapse"],
            },
        ),
        (
            "Timestamps",
            {
                "fields": ["created_at", "updated_at"],
                "classes": ["collapse"],
            },
        ),
    ]

    def package_link(self, obj):
        """Display package reference number as a link."""
        return obj.package.reference_number

    package_link.short_description = "Package"
    package_link.admin_order_field = "package__reference_number"

    def visibility_badge(self, obj):
        """Display visibility as a colored badge."""
        colors = {
            "all": "#22c55e",
            "office_only": "#f59e0b",
        }
        return format_html(
            '<span style="background-color: {}; color: white; '
            'padding: 2px 8px; border-radius: 4px;">{}</span>',
            colors.get(obj.visibility, "#9ca3af"),
            obj.get_visibility_display(),
        )

    visibility_badge.short_description = "Visibility"


@admin.register(Mention)
class MentionAdmin(admin.ModelAdmin):
    """Admin for Mention model."""

    list_display = ["id", "comment_link", "mentioned_user", "notified", "created_at"]
    list_filter = ["notified", "created_at"]
    search_fields = ["mentioned_user__email", "comment__content"]
    readonly_fields = ["created_at", "updated_at"]
    raw_id_fields = ["comment", "mentioned_user"]

    fieldsets = [
        (None, {"fields": ["comment", "mentioned_user"]}),
        ("Status", {"fields": ["notified"]}),
        (
            "Timestamps",
            {
                "fields": ["created_at", "updated_at"],
                "classes": ["collapse"],
            },
        ),
    ]

    def comment_link(self, obj):
        """Display truncated comment content."""
        content = obj.comment.content
        return content[:50] + "..." if len(content) > 50 else content

    comment_link.short_description = "Comment"


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    """Admin for Notification model."""

    list_display = [
        "id",
        "user",
        "notification_type_badge",
        "title",
        "is_read",
        "email_sent",
        "created_at",
    ]
    list_filter = ["notification_type", "is_read", "email_sent", "created_at"]
    search_fields = ["user__email", "title", "message", "package__reference_number"]
    readonly_fields = ["created_at", "updated_at", "read_at", "email_sent_at"]
    raw_id_fields = ["user", "package", "comment"]
    date_hierarchy = "created_at"

    fieldsets = [
        (None, {"fields": ["user", "notification_type"]}),
        ("Content", {"fields": ["title", "message", "link"]}),
        ("Related Objects", {"fields": ["package", "comment"]}),
        ("Read Status", {"fields": ["is_read", "read_at"]}),
        ("Email Status", {"fields": ["email_sent", "email_sent_at"]}),
        (
            "Timestamps",
            {
                "fields": ["created_at", "updated_at"],
                "classes": ["collapse"],
            },
        ),
    ]

    actions = ["mark_as_read", "mark_as_unread"]

    def notification_type_badge(self, obj):
        """Display notification type as a colored badge."""
        color_map = {
            "package_arrived": "#3b82f6",
            "action_required": "#ef4444",
            "comment_added": "#22c55e",
            "comment_mention": "#8b5cf6",
            "signature_required": "#f59e0b",
            "signature_removed": "#f97316",
            "integrity_violation": "#dc2626",
            "membership_approved": "#22c55e",
            "membership_rejected": "#ef4444",
            "membership_request": "#3b82f6",
            "package_completed": "#22c55e",
            "package_returned": "#f59e0b",
            "package_rejected": "#ef4444",
        }
        return format_html(
            '<span style="background-color: {}; color: white; '
            'padding: 2px 8px; border-radius: 4px; font-size: 11px;">{}</span>',
            color_map.get(obj.notification_type, "#9ca3af"),
            obj.get_notification_type_display(),
        )

    notification_type_badge.short_description = "Type"

    def mark_as_read(self, request, queryset):
        """Mark selected notifications as read."""
        from django.utils import timezone

        updated = queryset.filter(is_read=False).update(
            is_read=True, read_at=timezone.now()
        )
        self.message_user(request, f"{updated} notification(s) marked as read.")

    mark_as_read.short_description = "Mark selected as read"

    def mark_as_unread(self, request, queryset):
        """Mark selected notifications as unread."""
        updated = queryset.filter(is_read=True).update(is_read=False, read_at=None)
        self.message_user(request, f"{updated} notification(s) marked as unread.")

    mark_as_unread.short_description = "Mark selected as unread"


@admin.register(NotificationPreference)
class NotificationPreferenceAdmin(admin.ModelAdmin):
    """Admin for NotificationPreference model."""

    list_display = [
        "user",
        "in_app_enabled",
        "email_package_arrived",
        "email_action_required",
        "email_comments",
        "email_mentions",
        "email_digest",
        "updated_at",
    ]
    list_filter = [
        "in_app_enabled",
        "email_package_arrived",
        "email_action_required",
        "email_comments",
        "email_mentions",
        "email_signatures",
        "email_memberships",
        "email_digest",
    ]
    search_fields = ["user__email"]
    readonly_fields = ["created_at", "updated_at"]
    raw_id_fields = ["user"]

    fieldsets = [
        (None, {"fields": ["user"]}),
        ("In-App Notifications", {"fields": ["in_app_enabled"]}),
        (
            "Email Notifications",
            {
                "fields": [
                    "email_package_arrived",
                    "email_action_required",
                    "email_comments",
                    "email_mentions",
                    "email_signatures",
                    "email_memberships",
                    "email_digest",
                ]
            },
        ),
        (
            "Timestamps",
            {
                "fields": ["created_at", "updated_at"],
                "classes": ["collapse"],
            },
        ),
    ]
