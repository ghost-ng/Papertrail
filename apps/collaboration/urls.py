"""URL configuration for collaboration app."""

from django.urls import path

from apps.collaboration.views import (
    CommentListView,
    NotificationListView,
    add_comment,
    add_reply,
    mark_all_notifications_read,
    mark_notification_read,
    notification_count,
)

app_name = "collaboration"

urlpatterns = [
    # Comment URLs
    path(
        "packages/<int:package_id>/comments/",
        CommentListView.as_view(),
        name="comments",
    ),
    path(
        "packages/<int:package_id>/comments/add/",
        add_comment,
        name="add_comment",
    ),
    path(
        "comments/<int:comment_id>/reply/",
        add_reply,
        name="add_reply",
    ),
    # Notification URLs
    path(
        "notifications/",
        NotificationListView.as_view(),
        name="notifications",
    ),
    path(
        "notifications/<int:notification_id>/read/",
        mark_notification_read,
        name="mark_read",
    ),
    path(
        "notifications/mark-all-read/",
        mark_all_notifications_read,
        name="mark_all_read",
    ),
    path(
        "notifications/count/",
        notification_count,
        name="notification_count",
    ),
]
