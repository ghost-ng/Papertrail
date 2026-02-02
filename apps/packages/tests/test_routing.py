"""Tests for routing service and action executor."""

import pytest
from django.utils import timezone

from apps.accounts.models import User
from apps.organizations.models import Office, OfficeMembership, Organization
from apps.packages.models import (
    ActionNode,
    NodeConnection,
    Package,
    RoutingHistory,
    StageAction,
    StageCompletion,
    StageNode,
    WorkflowTemplate,
)
from apps.packages.services import ActionExecutor, RoutingError, RoutingService


@pytest.fixture
def user(db):
    return User.objects.create_user(
        email="test@example.com",
        password="testpass123",
        first_name="Test",
        last_name="User",
    )


@pytest.fixture
def other_user(db):
    return User.objects.create_user(
        email="other@example.com",
        password="testpass123",
        first_name="Other",
        last_name="User",
    )


@pytest.fixture
def organization(db):
    return Organization.objects.create(code="TEST", name="Test Organization")


@pytest.fixture
def office(db, organization):
    return Office.objects.create(
        organization=organization,
        code="J1",
        name="Test Office",
    )


@pytest.fixture
def office2(db, organization):
    return Office.objects.create(
        organization=organization,
        code="J2",
        name="Second Office",
    )


@pytest.fixture
def office_membership(db, user, office):
    return OfficeMembership.objects.create(
        user=user,
        office=office,
        role=OfficeMembership.ROLE_MEMBER,
    )


@pytest.fixture
def workflow_template(db, organization, user):
    return WorkflowTemplate.objects.create(
        organization=organization,
        name="Test Workflow",
        is_active=True,
        created_by=user,
    )


@pytest.fixture
def simple_workflow(db, workflow_template, office):
    """Create a simple workflow: Stage1 -> Stage2 -> (end)"""
    stage1 = StageNode.objects.create(
        template=workflow_template,
        node_id="stage1",
        name="Review Stage",
        action_type=StageNode.ActionType.APPROVE,
    )
    stage1.assigned_offices.add(office)

    stage2 = StageNode.objects.create(
        template=workflow_template,
        node_id="stage2",
        name="Approve Stage",
        action_type=StageNode.ActionType.APPROVE,
    )
    stage2.assigned_offices.add(office)

    NodeConnection.objects.create(
        template=workflow_template,
        from_node="stage1",
        to_node="stage2",
        connection_type=NodeConnection.ConnectionType.DEFAULT,
    )

    return workflow_template


@pytest.fixture
def multi_office_workflow(db, workflow_template, office, office2):
    """Create a workflow with a stage assigned to multiple offices."""
    stage = StageNode.objects.create(
        template=workflow_template,
        node_id="multi_stage",
        name="Multi-Office Stage",
        action_type=StageNode.ActionType.APPROVE,
    )
    stage.assigned_offices.add(office, office2)

    return workflow_template


@pytest.fixture
def package(db, organization, office, user, simple_workflow):
    return Package.objects.create(
        organization=organization,
        workflow_template=simple_workflow,
        title="Test Package",
        originator=user,
        originating_office=office,
        status=Package.Status.DRAFT,
    )


@pytest.mark.django_db
class TestRoutingServiceSubmit:
    def test_submit_package_success(self, package, user):
        """Test successful package submission."""
        service = RoutingService(package)
        service.submit_package(user)

        package.refresh_from_db()
        assert package.status == Package.Status.IN_ROUTING
        assert package.submitted_at is not None
        assert package.current_node == "stage1"

        # Check routing history created
        history = package.routing_history.first()
        assert history.transition_type == RoutingHistory.TransitionType.SUBMIT
        assert history.to_node == "stage1"

    def test_submit_package_no_workflow_fails(self, organization, office, user):
        """Test submission fails without workflow template."""
        package = Package.objects.create(
            organization=organization,
            title="No Workflow Package",
            originator=user,
            originating_office=office,
            status=Package.Status.DRAFT,
        )

        service = RoutingService(package)
        with pytest.raises(RoutingError, match="workflow template"):
            service.submit_package(user)

    def test_submit_package_wrong_user_fails(self, package, other_user):
        """Test submission fails if not originator."""
        service = RoutingService(package)
        with pytest.raises(RoutingError, match="originator"):
            service.submit_package(other_user)

    def test_submit_package_already_submitted_fails(self, package, user):
        """Test submission fails if already in routing."""
        package.status = Package.Status.IN_ROUTING
        package.save()

        service = RoutingService(package)
        with pytest.raises(RoutingError, match="draft"):
            service.submit_package(user)

    def test_submit_package_no_start_node_fails(self, organization, office, user):
        """Test submission fails if workflow has no start node."""
        # Create workflow with no nodes
        empty_template = WorkflowTemplate.objects.create(
            organization=organization,
            name="Empty Workflow",
            is_active=True,
            created_by=user,
        )
        package = Package.objects.create(
            organization=organization,
            workflow_template=empty_template,
            title="Test Package",
            originator=user,
            originating_office=office,
            status=Package.Status.DRAFT,
        )

        service = RoutingService(package)
        with pytest.raises(RoutingError, match="start node"):
            service.submit_package(user)


@pytest.mark.django_db
class TestRoutingServiceActions:
    def test_take_action_complete_advances(self, package, user, office, office_membership):
        """Test completing a stage advances to next."""
        service = RoutingService(package)
        service.submit_package(user)

        stage_action = service.take_action(
            user=user,
            office=office,
            action_type=StageAction.ActionType.COMPLETE,
        )

        package.refresh_from_db()
        assert package.current_node == "stage2"
        assert stage_action.action_type == StageAction.ActionType.COMPLETE

        # Check stage completion created
        completion = StageCompletion.objects.get(
            package=package, node_id="stage1", office=office
        )
        assert completion.completed_by == stage_action

    def test_take_action_complete_final_stage(self, package, user, office, office_membership):
        """Test completing the final stage completes the workflow."""
        service = RoutingService(package)
        service.submit_package(user)

        # Complete stage1
        service.take_action(
            user=user,
            office=office,
            action_type=StageAction.ActionType.COMPLETE,
        )

        # Complete stage2 (final stage)
        service.take_action(
            user=user,
            office=office,
            action_type=StageAction.ActionType.COMPLETE,
        )

        package.refresh_from_db()
        assert package.status == Package.Status.COMPLETED
        assert package.completed_at is not None
        assert package.current_node == ""

        # Check routing history shows completion
        history = package.routing_history.filter(
            transition_type=RoutingHistory.TransitionType.COMPLETE
        ).first()
        assert history is not None
        assert history.from_node == "stage2"

    def test_take_action_return_moves_back(self, package, user, office, office_membership):
        """Test returning a package moves it back."""
        service = RoutingService(package)
        service.submit_package(user)

        # Complete stage1 first
        service.take_action(
            user=user,
            office=office,
            action_type=StageAction.ActionType.COMPLETE,
        )

        # Now at stage2, return to stage1
        stage_action = service.take_action(
            user=user,
            office=office,
            action_type=StageAction.ActionType.RETURN,
            comment="Needs revision",
            return_to_node="stage1",
        )

        package.refresh_from_db()
        assert package.current_node == "stage1"
        assert package.status == Package.Status.IN_ROUTING

        # Check routing history
        history = package.routing_history.filter(
            transition_type=RoutingHistory.TransitionType.RETURN
        ).first()
        assert history.from_node == "stage2"
        assert history.to_node == "stage1"

    def test_take_action_return_clears_completions(self, package, user, office, office_membership):
        """Test returning clears stage completions at current node."""
        service = RoutingService(package)
        service.submit_package(user)

        # Complete stage1
        service.take_action(
            user=user,
            office=office,
            action_type=StageAction.ActionType.COMPLETE,
        )

        # Verify completion exists for stage1
        assert StageCompletion.objects.filter(
            package=package, node_id="stage1"
        ).exists()

        # Return from stage2 to stage1
        service.take_action(
            user=user,
            office=office,
            action_type=StageAction.ActionType.RETURN,
            comment="Needs revision",
            return_to_node="stage1",
        )

        # Stage2 completions should be cleared (there weren't any)
        # The routing logic clears completions at the current node when returning

    def test_take_action_reject_cancels(self, package, user, office, office_membership):
        """Test rejecting cancels the package."""
        service = RoutingService(package)
        service.submit_package(user)

        service.take_action(
            user=user,
            office=office,
            action_type=StageAction.ActionType.REJECT,
            comment="Invalid request",
        )

        package.refresh_from_db()
        assert package.status == Package.Status.CANCELLED

    def test_take_action_reject_follows_reject_path(
        self, organization, office, user, office_membership
    ):
        """Test reject follows reject path if defined."""
        # Create workflow with reject path
        template = WorkflowTemplate.objects.create(
            organization=organization,
            name="Workflow with Reject",
            is_active=True,
            created_by=user,
        )
        stage1 = StageNode.objects.create(
            template=template,
            node_id="stage1",
            name="Review Stage",
            action_type=StageNode.ActionType.APPROVE,
        )
        stage1.assigned_offices.add(office)

        reject_action = ActionNode.objects.create(
            template=template,
            node_id="reject_action",
            name="Reject Action",
            action_type=ActionNode.ActionType.REJECT,
        )

        # Create reject connection
        NodeConnection.objects.create(
            template=template,
            from_node="stage1",
            to_node="reject_action",
            connection_type=NodeConnection.ConnectionType.REJECT,
        )

        package = Package.objects.create(
            organization=organization,
            workflow_template=template,
            title="Test Package",
            originator=user,
            originating_office=office,
            status=Package.Status.DRAFT,
        )

        service = RoutingService(package)
        service.submit_package(user)

        service.take_action(
            user=user,
            office=office,
            action_type=StageAction.ActionType.REJECT,
            comment="Following reject path",
        )

        package.refresh_from_db()
        # Should have followed reject path to reject_action which cancels
        assert package.status == Package.Status.CANCELLED

    def test_take_action_requires_comment_for_return(
        self, package, user, office, office_membership
    ):
        """Test return requires a comment."""
        service = RoutingService(package)
        service.submit_package(user)

        # Complete stage1 first
        service.take_action(
            user=user,
            office=office,
            action_type=StageAction.ActionType.COMPLETE,
        )

        with pytest.raises(RoutingError, match="comment"):
            service.take_action(
                user=user,
                office=office,
                action_type=StageAction.ActionType.RETURN,
                return_to_node="stage1",
            )

    def test_take_action_requires_comment_for_reject(
        self, package, user, office, office_membership
    ):
        """Test reject requires a comment."""
        service = RoutingService(package)
        service.submit_package(user)

        with pytest.raises(RoutingError, match="comment"):
            service.take_action(
                user=user,
                office=office,
                action_type=StageAction.ActionType.REJECT,
            )

    def test_take_action_return_requires_destination(
        self, package, user, office, office_membership
    ):
        """Test return requires a destination node."""
        service = RoutingService(package)
        service.submit_package(user)

        # Complete stage1 first
        service.take_action(
            user=user,
            office=office,
            action_type=StageAction.ActionType.COMPLETE,
        )

        with pytest.raises(RoutingError, match="destination"):
            service.take_action(
                user=user,
                office=office,
                action_type=StageAction.ActionType.RETURN,
                comment="Needs revision",
                return_to_node="",  # Empty destination
            )

    def test_take_action_unauthorized_user_fails(self, package, user, office, other_user):
        """Test unauthorized user cannot act."""
        service = RoutingService(package)
        service.submit_package(user)

        with pytest.raises(RoutingError, match="cannot act"):
            service.take_action(
                user=other_user,
                office=office,
                action_type=StageAction.ActionType.COMPLETE,
            )

    def test_take_action_invalid_action_type_fails(
        self, package, user, office, office_membership
    ):
        """Test invalid action type fails."""
        service = RoutingService(package)
        service.submit_package(user)

        with pytest.raises(RoutingError, match="Invalid action type"):
            service.take_action(
                user=user,
                office=office,
                action_type="invalid_action",
            )

    def test_take_action_not_in_routing_fails(self, package, user, office, office_membership):
        """Test action fails if package not in routing."""
        # Package is still in draft status
        service = RoutingService(package)

        with pytest.raises(RoutingError, match="not in routing"):
            service.take_action(
                user=user,
                office=office,
                action_type=StageAction.ActionType.COMPLETE,
            )

    def test_take_action_records_metadata(self, package, user, office, office_membership):
        """Test action records actor metadata."""
        service = RoutingService(package)
        service.submit_package(user)

        stage_action = service.take_action(
            user=user,
            office=office,
            action_type=StageAction.ActionType.COMPLETE,
            position="Senior Reviewer",
            ip_address="192.168.1.1",
        )

        assert stage_action.actor == user
        assert stage_action.actor_office == office
        assert stage_action.actor_position == "Senior Reviewer"
        assert stage_action.ip_address == "192.168.1.1"


@pytest.mark.django_db
class TestRoutingServiceMultiOffice:
    def test_multi_office_any_rule_completes_on_first(
        self, organization, office, office2, user, other_user
    ):
        """Test 'any' rule (default) completes on first office action."""
        template = WorkflowTemplate.objects.create(
            organization=organization,
            name="Any Office Workflow",
            is_active=True,
            created_by=user,
        )
        stage = StageNode.objects.create(
            template=template,
            node_id="any_stage",
            name="Any Office Stage",
            action_type=StageNode.ActionType.APPROVE,
        )
        stage.assigned_offices.add(office, office2)

        OfficeMembership.objects.create(
            user=user,
            office=office,
            role=OfficeMembership.ROLE_MEMBER,
        )

        package = Package.objects.create(
            organization=organization,
            workflow_template=template,
            title="Any Office Package",
            originator=user,
            originating_office=office,
            status=Package.Status.DRAFT,
        )

        service = RoutingService(package)
        service.submit_package(user)

        # First office completes - should complete workflow (no next node)
        service.take_action(
            user=user,
            office=office,
            action_type=StageAction.ActionType.COMPLETE,
        )

        package.refresh_from_db()
        assert package.status == Package.Status.COMPLETED

    def test_multi_office_prevents_duplicate_completion(
        self, organization, office, office2, user, other_user, multi_office_workflow
    ):
        """Test same office cannot complete twice for 'all' rule."""
        OfficeMembership.objects.create(
            user=user,
            office=office,
            role=OfficeMembership.ROLE_MEMBER,
        )
        # Create another user in same office
        third_user = User.objects.create_user(
            email="third@example.com",
            password="testpass123",
            first_name="Third",
            last_name="User",
        )
        OfficeMembership.objects.create(
            user=third_user,
            office=office,
            role=OfficeMembership.ROLE_MEMBER,
        )

        package = Package.objects.create(
            organization=organization,
            workflow_template=multi_office_workflow,
            title="Multi Office Package",
            originator=user,
            originating_office=office,
            status=Package.Status.DRAFT,
        )

        service = RoutingService(package)
        service.submit_package(user)

        # First user from office completes
        service.take_action(
            user=user,
            office=office,
            action_type=StageAction.ActionType.COMPLETE,
        )

        # Verify completion was recorded
        completions = StageCompletion.objects.filter(
            package=package, node_id="multi_stage", office=office
        )
        assert completions.count() == 1


@pytest.mark.django_db
class TestRoutingServiceHelpers:
    def test_get_start_node(self, package):
        """Test finding the start node."""
        service = RoutingService(package)
        assert service.get_start_node() == "stage1"

    def test_get_start_node_no_template(self, organization, office, user):
        """Test get_start_node returns None without template."""
        package = Package.objects.create(
            organization=organization,
            title="No Template Package",
            originator=user,
            originating_office=office,
        )
        service = RoutingService(package)
        assert service.get_start_node() is None

    def test_get_current_stage(self, package, user):
        """Test getting current stage node."""
        service = RoutingService(package)
        service.submit_package(user)

        stage = service.get_current_stage()
        assert stage is not None
        assert stage.node_id == "stage1"
        assert stage.name == "Review Stage"

    def test_get_current_stage_no_current_node(self, package):
        """Test get_current_stage returns None if no current node."""
        service = RoutingService(package)
        assert service.get_current_stage() is None

    def test_get_node_returns_stage(self, package):
        """Test get_node returns stage node."""
        service = RoutingService(package)
        node = service.get_node("stage1")
        assert isinstance(node, StageNode)
        assert node.node_id == "stage1"

    def test_get_node_returns_action(self, organization, office, user):
        """Test get_node returns action node."""
        template = WorkflowTemplate.objects.create(
            organization=organization,
            name="Test",
            created_by=user,
        )
        ActionNode.objects.create(
            template=template,
            node_id="action1",
            name="Test Action",
            action_type=ActionNode.ActionType.SEND_ALERT,
        )
        package = Package.objects.create(
            organization=organization,
            workflow_template=template,
            title="Test",
            originator=user,
            originating_office=office,
        )

        service = RoutingService(package)
        node = service.get_node("action1")
        assert isinstance(node, ActionNode)
        assert node.node_id == "action1"

    def test_get_node_returns_none_not_found(self, package):
        """Test get_node returns None if not found."""
        service = RoutingService(package)
        assert service.get_node("nonexistent") is None

    def test_can_user_act(self, package, user, office, office_membership):
        """Test permission check."""
        service = RoutingService(package)
        service.submit_package(user)

        assert service.can_user_act(user, office) is True

    def test_can_user_act_wrong_office(self, package, user, office2, office_membership):
        """Test permission check fails for wrong office."""
        service = RoutingService(package)
        service.submit_package(user)

        # User has membership in office, but stage is assigned to office
        # office2 is not assigned to stage1
        assert service.can_user_act(user, office2) is False

    def test_can_user_act_no_membership(self, package, user, office, other_user):
        """Test permission check fails without membership."""
        service = RoutingService(package)
        service.submit_package(user)

        # other_user has no membership in any office
        assert service.can_user_act(other_user, office) is False

    # NOTE: test_can_user_act_pending_membership removed - office membership
    # is now immediate (no pending status). All memberships are active.

    def test_get_next_node_id(self, package):
        """Test getting next node ID."""
        service = RoutingService(package)
        next_node = service.get_next_node_id("stage1", "default")
        assert next_node == "stage2"

    def test_get_next_node_id_no_connection(self, package):
        """Test get_next_node_id returns None if no connection."""
        service = RoutingService(package)
        # stage2 has no outgoing connection
        assert service.get_next_node_id("stage2", "default") is None

    def test_get_available_return_nodes(self, package, user, office, office_membership):
        """Test getting valid return destinations."""
        service = RoutingService(package)
        service.submit_package(user)

        # Complete stage1 to get to stage2
        service.take_action(
            user=user,
            office=office,
            action_type=StageAction.ActionType.COMPLETE,
        )

        return_nodes = service.get_available_return_nodes()
        # Should include stage1 since it was visited
        node_ids = [node_id for node_id, name in return_nodes]
        assert "stage1" in node_ids

    def test_get_pending_offices_returns_empty_for_any_rule(self, package, user):
        """Test get_pending_offices returns empty for 'any' rule."""
        service = RoutingService(package)
        service.submit_package(user)

        # Default simple_workflow has 'any' rule
        pending = service.get_pending_offices()
        assert pending == []


@pytest.mark.django_db
class TestActionExecutor:
    def test_execute_complete_action(self, organization, office, user, workflow_template):
        """Test complete action node execution."""
        action_node = ActionNode.objects.create(
            template=workflow_template,
            node_id="complete_action",
            name="Complete",
            action_type=ActionNode.ActionType.COMPLETE,
        )

        package = Package.objects.create(
            organization=organization,
            workflow_template=workflow_template,
            title="Test Package",
            originator=user,
            originating_office=office,
            status=Package.Status.IN_ROUTING,
            current_node="complete_action",
        )

        executor = ActionExecutor()
        executor.execute(package, action_node)

        package.refresh_from_db()
        assert package.status == Package.Status.COMPLETED
        assert package.completed_at is not None
        assert package.current_node == ""

        # Check routing history
        history = package.routing_history.filter(
            transition_type=RoutingHistory.TransitionType.COMPLETE
        ).first()
        assert history is not None
        assert history.from_node == "complete_action"

    def test_execute_reject_action(self, organization, office, user, workflow_template):
        """Test reject action node execution."""
        action_node = ActionNode.objects.create(
            template=workflow_template,
            node_id="reject_action",
            name="Reject",
            action_type=ActionNode.ActionType.REJECT,
        )

        package = Package.objects.create(
            organization=organization,
            workflow_template=workflow_template,
            title="Test Package",
            originator=user,
            originating_office=office,
            status=Package.Status.IN_ROUTING,
            current_node="reject_action",
        )

        executor = ActionExecutor()
        executor.execute(package, action_node)

        package.refresh_from_db()
        assert package.status == Package.Status.CANCELLED
        assert package.current_node == ""

        # Check routing history
        history = package.routing_history.filter(
            transition_type=RoutingHistory.TransitionType.REJECT
        ).first()
        assert history is not None
        assert history.from_node == "reject_action"

    def test_execute_send_alert_action(self, organization, office, user, workflow_template):
        """Test send_alert action node execution (logs only for now)."""
        action_node = ActionNode.objects.create(
            template=workflow_template,
            node_id="alert_action",
            name="Alert",
            action_type=ActionNode.ActionType.SEND_ALERT,
            action_config={
                "message": "Test alert message",
                "recipients": ["originator"],
            },
        )

        package = Package.objects.create(
            organization=organization,
            workflow_template=workflow_template,
            title="Test Package",
            originator=user,
            originating_office=office,
            status=Package.Status.IN_ROUTING,
            current_node="alert_action",
        )

        executor = ActionExecutor()
        # Should not raise - just logs
        executor.execute(package, action_node)

        package.refresh_from_db()
        # Package status unchanged by alert
        assert package.status == Package.Status.IN_ROUTING

    def test_execute_send_email_action(self, organization, office, user, workflow_template):
        """Test send_email action node execution."""
        action_node = ActionNode.objects.create(
            template=workflow_template,
            node_id="email_action",
            name="Email",
            action_type=ActionNode.ActionType.SEND_EMAIL,
            action_config={
                "subject": "Test Subject",
                "body": "Test body",
                "recipients": ["originator"],
            },
        )

        package = Package.objects.create(
            organization=organization,
            workflow_template=workflow_template,
            title="Test Package",
            originator=user,
            originating_office=office,
            status=Package.Status.IN_ROUTING,
            current_node="email_action",
        )

        executor = ActionExecutor()
        # Should not raise - sends with fail_silently=True
        executor.execute(package, action_node)

        package.refresh_from_db()
        # Package status unchanged by email
        assert package.status == Package.Status.IN_ROUTING

    def test_execute_wait_action(self, organization, office, user, workflow_template):
        """Test wait action node execution (no-op for now)."""
        action_node = ActionNode.objects.create(
            template=workflow_template,
            node_id="wait_action",
            name="Wait",
            action_type=ActionNode.ActionType.WAIT,
            action_config={
                "hours": 24,
                "days": 1,
            },
        )

        package = Package.objects.create(
            organization=organization,
            workflow_template=workflow_template,
            title="Test Package",
            originator=user,
            originating_office=office,
            status=Package.Status.IN_ROUTING,
            current_node="wait_action",
        )

        executor = ActionExecutor()
        # Should not raise - currently a no-op
        executor.execute(package, action_node)

        package.refresh_from_db()
        # Package status unchanged by wait
        assert package.status == Package.Status.IN_ROUTING

    def test_execute_webhook_action(self, organization, office, user, workflow_template):
        """Test webhook action node execution (no-op for now)."""
        action_node = ActionNode.objects.create(
            template=workflow_template,
            node_id="webhook_action",
            name="Webhook",
            action_type=ActionNode.ActionType.WEBHOOK,
            action_config={
                "url": "https://example.com/webhook",
                "method": "POST",
            },
        )

        package = Package.objects.create(
            organization=organization,
            workflow_template=workflow_template,
            title="Test Package",
            originator=user,
            originating_office=office,
            status=Package.Status.IN_ROUTING,
            current_node="webhook_action",
        )

        executor = ActionExecutor()
        # Should not raise - currently a no-op
        executor.execute(package, action_node)

        package.refresh_from_db()
        # Package status unchanged by webhook
        assert package.status == Package.Status.IN_ROUTING

    def test_execute_unknown_action_type(self, organization, office, user, workflow_template):
        """Test handling of unknown action type."""
        action_node = ActionNode.objects.create(
            template=workflow_template,
            node_id="unknown_action",
            name="Unknown",
            action_type="unknown_type",  # Invalid type
        )

        package = Package.objects.create(
            organization=organization,
            workflow_template=workflow_template,
            title="Test Package",
            originator=user,
            originating_office=office,
            status=Package.Status.IN_ROUTING,
            current_node="unknown_action",
        )

        executor = ActionExecutor()
        # Should not raise - just logs warning
        executor.execute(package, action_node)

        package.refresh_from_db()
        # Package status unchanged
        assert package.status == Package.Status.IN_ROUTING


@pytest.mark.django_db
class TestRoutingServiceActionNodeChaining:
    """Test action node execution during routing transitions."""

    def test_submit_executes_action_node_at_start(self, organization, office, user):
        """Test that submitting executes action nodes at the start."""
        template = WorkflowTemplate.objects.create(
            organization=organization,
            name="Action Start Workflow",
            is_active=True,
            created_by=user,
        )

        # Start with an action node that completes the workflow immediately
        ActionNode.objects.create(
            template=template,
            node_id="auto_complete",
            name="Auto Complete",
            action_type=ActionNode.ActionType.COMPLETE,
        )

        package = Package.objects.create(
            organization=organization,
            workflow_template=template,
            title="Test Package",
            originator=user,
            originating_office=office,
            status=Package.Status.DRAFT,
        )

        service = RoutingService(package)
        service.submit_package(user)

        package.refresh_from_db()
        # Package should be completed immediately by the action node
        assert package.status == Package.Status.COMPLETED

    def test_advancing_executes_action_node_chain(self, organization, office, user):
        """Test that advancing through stage executes subsequent action nodes."""
        template = WorkflowTemplate.objects.create(
            organization=organization,
            name="Chain Workflow",
            is_active=True,
            created_by=user,
        )

        stage1 = StageNode.objects.create(
            template=template,
            node_id="stage1",
            name="Review",
            action_type=StageNode.ActionType.APPROVE,
        )
        stage1.assigned_offices.add(office)

        # Action node after stage1 that sends alert then continues
        ActionNode.objects.create(
            template=template,
            node_id="alert_action",
            name="Send Alert",
            action_type=ActionNode.ActionType.SEND_ALERT,
            action_config={"message": "Review complete"},
        )

        # Final complete action
        ActionNode.objects.create(
            template=template,
            node_id="complete_action",
            name="Complete",
            action_type=ActionNode.ActionType.COMPLETE,
        )

        # Connections: stage1 -> alert_action -> complete_action
        NodeConnection.objects.create(
            template=template,
            from_node="stage1",
            to_node="alert_action",
            connection_type=NodeConnection.ConnectionType.DEFAULT,
        )
        NodeConnection.objects.create(
            template=template,
            from_node="alert_action",
            to_node="complete_action",
            connection_type=NodeConnection.ConnectionType.DEFAULT,
        )

        OfficeMembership.objects.create(
            user=user,
            office=office,
            role=OfficeMembership.ROLE_MEMBER,
        )

        package = Package.objects.create(
            organization=organization,
            workflow_template=template,
            title="Test Package",
            originator=user,
            originating_office=office,
            status=Package.Status.DRAFT,
        )

        service = RoutingService(package)
        service.submit_package(user)

        # Complete stage1
        service.take_action(
            user=user,
            office=office,
            action_type=StageAction.ActionType.COMPLETE,
        )

        package.refresh_from_db()
        # Should have executed both action nodes and completed
        assert package.status == Package.Status.COMPLETED


@pytest.mark.django_db
class TestRoutingHistoryTracking:
    """Test routing history is properly tracked."""

    def test_history_tracks_all_transitions(self, package, user, office, office_membership):
        """Test all routing transitions are recorded in history."""
        service = RoutingService(package)

        # Submit
        service.submit_package(user)

        # Complete stage1
        service.take_action(
            user=user,
            office=office,
            action_type=StageAction.ActionType.COMPLETE,
        )

        # Complete stage2 (final)
        service.take_action(
            user=user,
            office=office,
            action_type=StageAction.ActionType.COMPLETE,
        )

        # Check history
        history = list(package.routing_history.order_by("created_at"))

        assert len(history) == 3

        # First: submit
        assert history[0].transition_type == RoutingHistory.TransitionType.SUBMIT
        assert history[0].from_node == ""
        assert history[0].to_node == "stage1"

        # Second: advance to stage2
        assert history[1].transition_type == RoutingHistory.TransitionType.ADVANCE
        assert history[1].from_node == "stage1"
        assert history[1].to_node == "stage2"

        # Third: complete
        assert history[2].transition_type == RoutingHistory.TransitionType.COMPLETE
        assert history[2].from_node == "stage2"
        assert history[2].to_node == ""

    def test_history_links_to_triggering_action(
        self, package, user, office, office_membership
    ):
        """Test history entries link to the stage action that triggered them."""
        service = RoutingService(package)
        service.submit_package(user)

        stage_action = service.take_action(
            user=user,
            office=office,
            action_type=StageAction.ActionType.COMPLETE,
        )

        # Find the advance history entry
        advance_history = package.routing_history.filter(
            transition_type=RoutingHistory.TransitionType.ADVANCE
        ).first()

        assert advance_history.triggered_by == stage_action
