"""Action executor for automated workflow action nodes."""

import logging

from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone

from apps.collaboration.models import Notification
from apps.collaboration.services import NotificationService
from apps.packages.models import ActionNode, Package, RoutingHistory

logger = logging.getLogger(__name__)


class ActionExecutor:
    """Executes automated action nodes in workflows.

    Currently synchronous - will be moved to Celery tasks for production.
    See docs/PRODUCTION_BACKLOG.md for async migration plan.
    """

    def execute(self, package: Package, node: ActionNode) -> None:
        """Execute an action node based on its type."""
        action_type = node.action_type
        config = node.action_config or {}

        logger.info(
            f"Executing action node {node.node_id} ({action_type}) "
            f"for package {package.reference_number}"
        )

        handlers = {
            ActionNode.ActionType.SEND_ALERT: self._send_alert,
            ActionNode.ActionType.SEND_EMAIL: self._send_email,
            ActionNode.ActionType.COMPLETE: self._complete_workflow,
            ActionNode.ActionType.REJECT: self._reject_workflow,
            ActionNode.ActionType.WAIT: self._wait,
            ActionNode.ActionType.WEBHOOK: self._webhook,
        }

        handler = handlers.get(action_type)
        if handler:
            try:
                handler(package, node, config)
            except Exception as e:
                logger.error(
                    f"Error executing action {action_type} for package "
                    f"{package.reference_number}: {e}"
                )
                # Don't re-raise - action failures shouldn't block routing
        else:
            logger.warning(f"Unknown action type: {action_type}")

    def _send_alert(self, package: Package, node: ActionNode, config: dict) -> None:
        """Send an in-app notification.

        Config options:
        - recipients: list of user IDs or special values:
            - "originator" - the package originator
            - "current_office" - all members of the package's current stage offices
        - title: notification title (defaults to node name)
        - message: notification message template
        """
        from apps.accounts.models import User
        from apps.organizations.models import OfficeMembership

        title = config.get("title", node.name or "Workflow Alert")
        message = config.get("message", f"Alert for package {package.reference_number}")
        recipients = config.get("recipients", ["originator"])  # Default to originator
        link = f"/packages/{package.reference_number}/"

        users_to_notify = set()

        for recipient in recipients:
            if recipient == "originator":
                users_to_notify.add(package.originator)
            elif recipient == "current_office":
                # Get users from the current stage's assigned offices
                from apps.packages.services.routing import RoutingService

                routing = RoutingService(package)
                stage = routing.get_current_stage()
                if stage:
                    for office in stage.assigned_offices.all():
                        office_users = User.objects.filter(
                            office_memberships__office=office
                        )
                        users_to_notify.update(office_users)
            elif isinstance(recipient, int):
                try:
                    user = User.objects.get(pk=recipient)
                    users_to_notify.add(user)
                except User.DoesNotExist:
                    pass

        # Send notification to each user
        for user in users_to_notify:
            NotificationService.notify(
                user=user,
                notification_type=Notification.NotificationType.ACTION_REQUIRED,
                title=title,
                message=message,
                link=link,
                package=package,
                send_email=False,  # Alerts are in-app only
            )

        logger.info(
            f"Alert sent for package {package.reference_number} to {len(users_to_notify)} users"
        )

    def _send_email(self, package: Package, node: ActionNode, config: dict) -> None:
        """Send an email notification.

        Config options:
        - recipients: list of email addresses or "originator"
        - subject: email subject template
        - body: email body template
        """
        recipients = config.get("recipients", [])
        subject = config.get("subject", f"Package {package.reference_number} Update")
        body = config.get("body", f"Package {package.reference_number} has been updated.")

        # Handle special recipient values
        email_list = []
        for r in recipients:
            if r == "originator":
                email_list.append(package.originator.email)
            elif isinstance(r, str) and "@" in r:
                email_list.append(r)

        if email_list:
            try:
                send_mail(
                    subject=subject,
                    message=body,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=email_list,
                    fail_silently=True,  # Don't block workflow on email failure
                )
                logger.info(
                    f"Email sent for package {package.reference_number} to {email_list}"
                )
            except Exception as e:
                logger.error(f"Failed to send email: {e}")
        else:
            logger.warning(
                f"No valid recipients for email action on package {package.reference_number}"
            )

    def _complete_workflow(
        self, package: Package, node: ActionNode, config: dict
    ) -> None:
        """Mark the workflow as completed and notify the originator."""
        package.status = Package.Status.COMPLETED
        package.completed_at = timezone.now()
        package.current_node = ""
        package.save()

        # Create routing history entry
        RoutingHistory.objects.create(
            package=package,
            from_node=node.node_id,
            to_node="",
            transition_type=RoutingHistory.TransitionType.COMPLETE,
        )

        # Notify the originator
        NotificationService.notify(
            user=package.originator,
            notification_type=Notification.NotificationType.PACKAGE_COMPLETED,
            title="Package Completed",
            message=f"Your package {package.reference_number} has completed routing.",
            link=f"/packages/{package.reference_number}/",
            package=package,
            send_email=True,
        )

        logger.info(f"Workflow completed for package {package.reference_number}")

    def _reject_workflow(
        self, package: Package, node: ActionNode, config: dict
    ) -> None:
        """Mark the workflow as rejected/cancelled and notify the originator."""
        package.status = Package.Status.CANCELLED
        package.current_node = ""
        package.save()

        # Create routing history entry
        RoutingHistory.objects.create(
            package=package,
            from_node=node.node_id,
            to_node="",
            transition_type=RoutingHistory.TransitionType.REJECT,
        )

        # Notify the originator
        reason = config.get("reason", "")
        message = f"Your package {package.reference_number} has been rejected."
        if reason:
            message += f" Reason: {reason}"

        NotificationService.notify(
            user=package.originator,
            notification_type=Notification.NotificationType.PACKAGE_REJECTED,
            title="Package Rejected",
            message=message,
            link=f"/packages/{package.reference_number}/",
            package=package,
            send_email=True,
        )

        logger.info(f"Workflow rejected for package {package.reference_number}")

    def _wait(self, package: Package, node: ActionNode, config: dict) -> None:
        """Wait action - no-op for now, will be Celery delayed task.

        Config options:
        - hours: number of hours to wait
        - days: number of days to wait

        See docs/PRODUCTION_BACKLOG.md for Celery implementation.
        """
        hours = config.get("hours", 0)
        days = config.get("days", 0)

        # For now, just log and continue (no actual waiting)
        logger.info(
            f"WAIT action for package {package.reference_number}: "
            f"{days} days, {hours} hours (currently no-op, needs Celery)"
        )

    def _webhook(self, package: Package, node: ActionNode, config: dict) -> None:
        """Call an external webhook URL.

        Config options:
        - url: webhook URL
        - method: HTTP method (GET, POST)
        - headers: dict of headers

        See docs/PRODUCTION_BACKLOG.md for production implementation.
        """
        url = config.get("url", "")
        method = config.get("method", "POST")

        # For now, just log (actual HTTP calls deferred to production)
        logger.info(
            f"WEBHOOK action for package {package.reference_number}: "
            f"{method} {url} (currently no-op, see PRODUCTION_BACKLOG.md)"
        )
