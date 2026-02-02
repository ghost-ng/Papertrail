"""Views for collaboration app."""

from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View
from django.views.decorators.http import require_GET, require_POST

from apps.collaboration.forms import CommentForm
from apps.collaboration.models import Comment, Notification
from apps.collaboration.services import MentionService, NotificationService
from apps.organizations.models import OfficeMembership
from apps.packages.models import Package


def get_user_office_ids(user):
    """Get list of office IDs where user has membership."""
    return list(
        OfficeMembership.objects.filter(
            user=user,
        ).values_list("office_id", flat=True)
    )


class CommentListView(LoginRequiredMixin, View):
    """View for listing comments on a package."""

    def get(self, request, package_id):
        """
        GET /collaboration/packages/<package_id>/comments/
        Returns comments_partial.html with comments filtered by visibility.
        Office-only comments are only visible to office members.
        """
        package = get_object_or_404(Package, pk=package_id)
        user_office_ids = get_user_office_ids(request.user)

        # Filter comments: all visibility OR office-only where user is a member
        comments = Comment.objects.filter(
            package=package,
            parent__isnull=True,  # Only top-level comments
        ).filter(
            Q(visibility=Comment.Visibility.ALL)
            | Q(
                visibility=Comment.Visibility.OFFICE_ONLY,
                author_office_id__in=user_office_ids,
            )
        ).select_related(
            "author",
            "author_office",
        ).prefetch_related(
            "replies__author",
            "replies__author_office",
        ).order_by("-created_at")

        # Filter replies based on visibility as well
        filtered_comments = []
        for comment in comments:
            # Filter visible replies
            visible_replies = [
                reply
                for reply in comment.replies.all()
                if reply.visibility == Comment.Visibility.ALL
                or reply.author_office_id in user_office_ids
            ]
            comment.visible_replies = visible_replies
            filtered_comments.append(comment)

        form = CommentForm()

        context = {
            "package": package,
            "comments": filtered_comments,
            "form": form,
            "user_office_ids": user_office_ids,
        }

        return render(request, "collaboration/comments_partial.html", context)


@login_required
@require_POST
def add_comment(request, package_id):
    """
    POST /collaboration/packages/<package_id>/comments/add/
    Creates comment, processes mentions, notifies package originator.
    Redirects back to comments.
    """
    package = get_object_or_404(Package, pk=package_id)
    user_office_ids = get_user_office_ids(request.user)

    form = CommentForm(request.POST)
    if form.is_valid():
        comment = form.save(commit=False)
        comment.package = package
        comment.author = request.user

        # Get user's primary office (first membership)
        membership = OfficeMembership.objects.filter(
            user=request.user,
        ).select_related("office").first()

        if membership:
            comment.author_office = membership.office
        else:
            # User has no approved office membership
            return redirect("collaboration:comments", package_id=package_id)

        comment.save()

        # Process mentions in the comment
        MentionService.process_comment_mentions(comment)

        # Notify package originator (if not the commenter)
        if package.originator != request.user:
            NotificationService.notify(
                user=package.originator,
                notification_type=Notification.NotificationType.COMMENT_ADDED,
                title="New comment on your package",
                message=f"{request.user.email} commented on {package.reference_number}",
                link=f"/packages/{package.reference_number}/",
                package=package,
                comment=comment,
            )

    return redirect("collaboration:comments", package_id=package_id)


@login_required
@require_POST
def add_reply(request, comment_id):
    """
    POST /collaboration/comments/<comment_id>/reply/
    Creates reply, inherits visibility from parent.
    """
    parent_comment = get_object_or_404(Comment, pk=comment_id)
    package = parent_comment.package

    form = CommentForm(request.POST)
    if form.is_valid():
        reply = form.save(commit=False)
        reply.package = package
        reply.author = request.user
        reply.parent = parent_comment
        # Inherit visibility from parent
        reply.visibility = parent_comment.visibility

        # Get user's primary office
        membership = OfficeMembership.objects.filter(
            user=request.user,
        ).select_related("office").first()

        if membership:
            reply.author_office = membership.office
        else:
            return redirect("collaboration:comments", package_id=package.pk)

        reply.save()

        # Process mentions in the reply
        MentionService.process_comment_mentions(reply)

        # Notify parent comment author (if not the replier)
        if parent_comment.author != request.user:
            NotificationService.notify(
                user=parent_comment.author,
                notification_type=Notification.NotificationType.COMMENT_ADDED,
                title="Reply to your comment",
                message=f"{request.user.email} replied to your comment on {package.reference_number}",
                link=f"/packages/{package.reference_number}/",
                package=package,
                comment=reply,
            )

    return redirect("collaboration:comments", package_id=package.pk)


class NotificationListView(LoginRequiredMixin, View):
    """View for listing user notifications."""

    def get(self, request):
        """
        GET /collaboration/notifications/
        Shows user's notifications.
        """
        base_queryset = Notification.objects.filter(user=request.user)
        unread_count = base_queryset.filter(is_read=False).count()

        notifications = base_queryset.select_related(
            "package",
            "comment",
        ).order_by("-created_at")[:50]  # Limit to recent 50

        context = {
            "notifications": notifications,
            "unread_count": unread_count,
        }

        return render(request, "collaboration/notifications.html", context)


@login_required
@require_POST
def mark_notification_read(request, notification_id):
    """
    POST /collaboration/notifications/<id>/read/
    Returns JSON.
    """
    notification = get_object_or_404(
        Notification,
        pk=notification_id,
        user=request.user,
    )
    notification.mark_read()

    return JsonResponse({
        "success": True,
        "notification_id": notification_id,
    })


@login_required
@require_POST
def mark_all_notifications_read(request):
    """
    POST /collaboration/notifications/mark-all-read/
    Returns JSON.
    """
    count = NotificationService.mark_all_read(request.user)

    return JsonResponse({
        "success": True,
        "count": count,
    })


@login_required
@require_GET
def notification_count(request):
    """
    GET /collaboration/notifications/count/
    Returns JSON with unread count.
    """
    count = NotificationService.get_unread_count(request.user)

    return JsonResponse({
        "unread_count": count,
    })
