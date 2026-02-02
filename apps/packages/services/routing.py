"""Routing service for package workflow processing."""

from django.db import transaction
from django.utils import timezone

from apps.collaboration.models import Notification
from apps.collaboration.services import NotificationService
from apps.packages.models import (
    ActionNode,
    NodeConnection,
    Package,
    RoutingHistory,
    StageAction,
    StageCompletion,
    StageNode,
)


class RoutingError(Exception):
    """Base exception for routing errors."""

    pass


class RoutingService:
    """Handles all package routing operations."""

    def __init__(self, package: Package):
        self.package = package
        self.template = package.workflow_template

    def get_start_node(self) -> str | None:
        """Find the workflow start node (node with no incoming connections)."""
        if not self.template:
            return None

        all_stage_nodes = set(
            self.template.stagenode_nodes.values_list("node_id", flat=True)
        )
        all_action_nodes = set(
            self.template.actionnode_nodes.values_list("node_id", flat=True)
        )
        all_nodes = all_stage_nodes | all_action_nodes

        to_nodes = set(self.template.connections.values_list("to_node", flat=True))

        start_nodes = all_nodes - to_nodes
        # Prefer stage nodes as start
        stage_starts = start_nodes & all_stage_nodes
        if stage_starts:
            return stage_starts.pop()
        return start_nodes.pop() if start_nodes else None

    def get_current_stage(self) -> StageNode | None:
        """Get the current stage node."""
        if not self.template or not self.package.current_node:
            return None
        return self.template.stagenode_nodes.filter(
            node_id=self.package.current_node
        ).first()

    def get_node(self, node_id: str) -> StageNode | ActionNode | None:
        """Get a node by ID (stage or action)."""
        if not self.template:
            return None
        node = self.template.stagenode_nodes.filter(node_id=node_id).first()
        if node:
            return node
        return self.template.actionnode_nodes.filter(node_id=node_id).first()

    def get_next_node_id(
        self, from_node: str, connection_type: str = "default"
    ) -> str | None:
        """Get the next node ID following a specific connection type."""
        if not self.template:
            return None
        connection = self.template.connections.filter(
            from_node=from_node, connection_type=connection_type
        ).first()
        return connection.to_node if connection else None

    def get_available_return_nodes(self) -> list[tuple[str, str]]:
        """Get valid return destinations (node_id, name) for current stage."""
        if not self.template or not self.package.current_node:
            return []

        # Get all previous stage actions for this package
        visited_nodes = list(
            self.package.routing_history.exclude(from_node="")
            .values_list("from_node", flat=True)
            .distinct()
        )

        # Return stage nodes that were previously visited
        return list(
            self.template.stagenode_nodes.filter(node_id__in=visited_nodes).values_list(
                "node_id", "name"
            )
        )

    def can_user_act(self, user, office) -> bool:
        """Check if user can take action at current stage.

        Returns True if:
        - There is a current stage
        - The office is assigned to this stage
        - The user is a member of the office
        - The office hasn't already completed this stage (for 'all' rule)
        """
        stage = self.get_current_stage()
        if not stage:
            return False

        # Check if office is assigned to this stage
        if not stage.assigned_offices.filter(pk=office.pk).exists():
            return False

        # For 'all' rule stages, check if this office already completed
        if stage.multi_office_rule == StageNode.MultiOfficeRule.ALL:
            if StageCompletion.objects.filter(
                package=self.package, node_id=stage.node_id, office=office
            ).exists():
                return False  # Office already acted

        # Check if user is a member of the office
        from apps.organizations.models import OfficeMembership

        return OfficeMembership.objects.filter(user=user, office=office).exists()

    def get_pending_offices(self) -> list:
        """Get offices that haven't completed the current stage yet.

        Returns a list of Office objects that are assigned to the current stage
        but haven't yet completed it. Empty list if stage uses 'any' rule or
        all offices have completed.
        """
        stage = self.get_current_stage()
        if not stage:
            return []

        # For 'any' rule, no need to track pending - first completion advances
        if stage.multi_office_rule == StageNode.MultiOfficeRule.ANY:
            return []

        # For 'all' rule, get offices that haven't completed yet
        assigned_office_ids = set(stage.assigned_offices.values_list("id", flat=True))
        completed_office_ids = set(
            StageCompletion.objects.filter(
                package=self.package, node_id=stage.node_id
            ).values_list("office_id", flat=True)
        )
        pending_office_ids = assigned_office_ids - completed_office_ids

        from apps.organizations.models import Office

        return list(Office.objects.filter(id__in=pending_office_ids))

    def is_stage_complete(self, stage: StageNode) -> bool:
        """Check if a stage has been fully completed based on its multi_office_rule."""
        if stage.multi_office_rule == StageNode.MultiOfficeRule.ANY:
            # Any completion counts - check if at least one completion exists
            return StageCompletion.objects.filter(
                package=self.package, node_id=stage.node_id
            ).exists()
        else:
            # All offices must complete
            assigned_count = stage.assigned_offices.count()
            if assigned_count == 0:
                return True  # No offices assigned = auto-complete
            completed_count = StageCompletion.objects.filter(
                package=self.package, node_id=stage.node_id
            ).count()
            return completed_count >= assigned_count

    @transaction.atomic
    def submit_package(self, user) -> None:
        """Submit a draft package into routing."""
        if self.package.status != Package.Status.DRAFT:
            raise RoutingError("Package must be in draft status to submit")

        if not self.template:
            raise RoutingError("Package must have a workflow template")

        if self.package.originator != user:
            raise RoutingError("Only the originator can submit this package")

        start_node = self.get_start_node()
        if not start_node:
            raise RoutingError("Workflow has no start node")

        # Update package
        self.package.status = Package.Status.IN_ROUTING
        self.package.submitted_at = timezone.now()
        self.package.current_node = start_node
        self.package.save()

        # Create routing history entry
        RoutingHistory.objects.create(
            package=self.package,
            from_node="",
            to_node=start_node,
            transition_type=RoutingHistory.TransitionType.SUBMIT,
        )

        # Execute any action nodes at start
        self._execute_action_nodes_from(start_node)

    @transaction.atomic
    def take_action(
        self,
        user,
        office,
        action_type: str,
        comment: str = "",
        return_to_node: str = "",
        position: str = "",
        ip_address: str | None = None,
    ) -> StageAction:
        """Process a stage action (complete/return/reject)."""
        if self.package.status != Package.Status.IN_ROUTING:
            raise RoutingError("Package is not in routing")

        if not self.can_user_act(user, office):
            raise RoutingError("User cannot act at this stage")

        stage = self.get_current_stage()
        if not stage:
            raise RoutingError("No current stage")

        # Validate action type
        valid_action_types = [choice[0] for choice in StageAction.ActionType.choices]
        if action_type not in valid_action_types:
            raise RoutingError(f"Invalid action type: {action_type}")

        # Require comment for return/reject
        if action_type in (StageAction.ActionType.RETURN, StageAction.ActionType.REJECT):
            if not comment.strip():
                raise RoutingError(f"{action_type.title()} requires a comment")

        # Validate return_to_node for returns
        if action_type == StageAction.ActionType.RETURN:
            if not return_to_node:
                raise RoutingError("Return action requires a destination node")

        # Create stage action record
        stage_action = StageAction.objects.create(
            package=self.package,
            node_id=stage.node_id,
            actor=user,
            actor_office=office,
            actor_position=position,
            action_type=action_type,
            comment=comment,
            return_to_node=return_to_node,
            ip_address=ip_address,
        )

        # Handle the action
        if action_type == StageAction.ActionType.COMPLETE:
            self._handle_complete(stage_action, stage)
        elif action_type == StageAction.ActionType.RETURN:
            self._handle_return(stage_action, return_to_node)
        elif action_type == StageAction.ActionType.REJECT:
            self._handle_reject(stage_action, stage)

        return stage_action

    def _handle_complete(self, stage_action: StageAction, stage: StageNode) -> None:
        """Handle a complete action.

        Creates a completion record for the acting office. For multi-office stages:
        - 'any' rule: Advances immediately on first completion
        - 'all' rule: Only advances when all assigned offices have completed
        """
        # Create stage completion record for this office
        StageCompletion.objects.create(
            package=self.package,
            node_id=stage.node_id,
            office=stage_action.actor_office,
            completed_by=stage_action,
        )

        # Check if stage is fully complete based on multi_office_rule
        if self.is_stage_complete(stage):
            # Advance to next node
            self._advance_to_next(stage_action, "default")
        # else: Stage stays at current node, waiting for other offices

    def _handle_return(self, stage_action: StageAction, return_to_node: str) -> None:
        """Handle a return action."""
        from_node = self.package.current_node

        # Clear any stage completions at current node
        StageCompletion.objects.filter(
            package=self.package, node_id=from_node
        ).delete()

        # Move to return destination
        self.package.current_node = return_to_node
        self.package.save()

        RoutingHistory.objects.create(
            package=self.package,
            from_node=from_node,
            to_node=return_to_node,
            transition_type=RoutingHistory.TransitionType.RETURN,
            triggered_by=stage_action,
        )

    def _handle_reject(self, stage_action: StageAction, stage: StageNode) -> None:
        """Handle a reject action."""
        from_node = self.package.current_node

        # Check for reject path in workflow
        reject_node = self.get_next_node_id(from_node, "reject")

        if reject_node:
            # Follow reject path
            self.package.current_node = reject_node
            self.package.save()

            RoutingHistory.objects.create(
                package=self.package,
                from_node=from_node,
                to_node=reject_node,
                transition_type=RoutingHistory.TransitionType.REJECT,
                triggered_by=stage_action,
            )

            self._execute_action_nodes_from(reject_node)
        else:
            # No reject path - cancel the package
            self.package.status = Package.Status.CANCELLED
            self.package.save()

            RoutingHistory.objects.create(
                package=self.package,
                from_node=from_node,
                to_node="",
                transition_type=RoutingHistory.TransitionType.REJECT,
                triggered_by=stage_action,
            )

    def _advance_to_next(
        self, stage_action: StageAction, connection_type: str
    ) -> None:
        """Advance package to the next node."""
        from_node = self.package.current_node
        next_node = self.get_next_node_id(from_node, connection_type)

        if not next_node:
            # No next node - workflow complete
            self.package.status = Package.Status.COMPLETED
            self.package.completed_at = timezone.now()
            self.package.current_node = ""
            self.package.save()

            RoutingHistory.objects.create(
                package=self.package,
                from_node=from_node,
                to_node="",
                transition_type=RoutingHistory.TransitionType.COMPLETE,
                triggered_by=stage_action,
            )
            return

        self.package.current_node = next_node
        self.package.save()

        RoutingHistory.objects.create(
            package=self.package,
            from_node=from_node,
            to_node=next_node,
            transition_type=RoutingHistory.TransitionType.ADVANCE,
            triggered_by=stage_action,
        )

        # Execute any action nodes
        self._execute_action_nodes_from(next_node)

    def _execute_action_nodes_from(self, node_id: str) -> None:
        """Execute action nodes starting from a node, continuing through the chain.

        If the node is a stage node, sends notifications to assigned offices.
        If the node is an action node, executes it and continues to the next node.
        """
        node = self.get_node(node_id)

        # If it's a stage node, notify assigned offices and stop
        if isinstance(node, StageNode):
            self._notify_stage_offices(node)
            return

        # If it's not an action node either, stop
        if not isinstance(node, ActionNode):
            return

        # Execute this action node
        from apps.packages.services.actions import ActionExecutor

        executor = ActionExecutor()
        executor.execute(self.package, node)

        # If the action completed/rejected the workflow, stop
        if self.package.status in (Package.Status.COMPLETED, Package.Status.CANCELLED):
            return

        # Continue to next node
        next_node_id = self.get_next_node_id(node_id, "default")
        if next_node_id:
            self.package.current_node = next_node_id
            self.package.save()

            RoutingHistory.objects.create(
                package=self.package,
                from_node=node_id,
                to_node=next_node_id,
                transition_type=RoutingHistory.TransitionType.ADVANCE,
            )

            # Recursively process next action nodes
            self._execute_action_nodes_from(next_node_id)

    def _notify_stage_offices(self, stage: StageNode) -> None:
        """Notify all members of assigned offices that a package requires action.

        Sends PACKAGE_ARRIVED notifications to all office members.
        """
        link = f"/packages/{self.package.reference_number}/"
        title = "Package Requires Action"
        message = (
            f"Package {self.package.reference_number} has arrived at "
            f"{stage.name} ({stage.get_action_type_display()}) and requires your action."
        )

        for office in stage.assigned_offices.all():
            NotificationService.notify_office(
                office=office,
                notification_type=Notification.NotificationType.PACKAGE_ARRIVED,
                title=title,
                message=message,
                link=link,
                package=self.package,
            )
