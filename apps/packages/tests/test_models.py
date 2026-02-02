"""Tests for Package, Tab, Document, and Workflow models."""

import pytest
from django.utils import timezone
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.accounts.models import User
from apps.organizations.models import Organization, Office
from apps.packages.models import (
    Package,
    Tab,
    Document,
    WorkflowTemplate,
    WorkflowNode,
    StageNode,
    ActionNode,
    NodeConnection,
)


@pytest.fixture
def user(db):
    return User.objects.create_user(
        email="test@example.com",
        password="testpass123",
        first_name="Test",
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


@pytest.mark.django_db
class TestPackageModel:
    def test_create_package(self, user, organization, office):
        """Test basic package creation."""
        from apps.packages.models import Package

        package = Package.objects.create(
            organization=organization,
            title="Test Package",
            originator=user,
            originating_office=office,
        )
        assert package.pk is not None
        assert package.status == "draft"
        assert package.priority == "normal"

    def test_reference_number_auto_generated(self, user, organization, office):
        """Test reference number is auto-generated on save."""
        from apps.packages.models import Package

        package = Package.objects.create(
            organization=organization,
            title="Test Package",
            originator=user,
            originating_office=office,
        )
        # Format: ORG-YEAR-NNNNN (e.g., TEST-2025-00001)
        assert package.reference_number.startswith(f"{organization.code}-")
        assert str(timezone.now().year) in package.reference_number

    def test_reference_number_sequential(self, user, organization, office):
        """Test reference numbers are sequential within org/year."""
        from apps.packages.models import Package

        pkg1 = Package.objects.create(
            organization=organization,
            title="Package 1",
            originator=user,
            originating_office=office,
        )
        pkg2 = Package.objects.create(
            organization=organization,
            title="Package 2",
            originator=user,
            originating_office=office,
        )
        # Extract sequence numbers
        seq1 = int(pkg1.reference_number.split("-")[-1])
        seq2 = int(pkg2.reference_number.split("-")[-1])
        assert seq2 == seq1 + 1

    def test_priority_choices(self, user, organization, office):
        """Test priority field accepts valid choices."""
        from apps.packages.models import Package

        for priority in ["low", "normal", "urgent"]:
            package = Package.objects.create(
                organization=organization,
                title=f"Package {priority}",
                originator=user,
                originating_office=office,
                priority=priority,
            )
            assert package.priority == priority

    def test_status_choices(self, user, organization, office):
        """Test status field accepts valid choices."""
        from apps.packages.models import Package

        package = Package.objects.create(
            organization=organization,
            title="Test Package",
            originator=user,
            originating_office=office,
        )
        valid_statuses = ["draft", "in_routing", "completed", "cancelled", "on_hold", "archived"]
        for status in valid_statuses:
            package.status = status
            package.save()
            package.refresh_from_db()
            assert package.status == status

    def test_str_method(self, user, organization, office):
        """Test string representation."""
        from apps.packages.models import Package

        package = Package.objects.create(
            organization=organization,
            title="Important Document",
            originator=user,
            originating_office=office,
        )
        assert package.reference_number in str(package)
        assert "Important Document" in str(package)


@pytest.fixture
def package(db, user, organization, office):
    return Package.objects.create(
        organization=organization,
        title="Test Package",
        originator=user,
        originating_office=office,
    )


@pytest.fixture
def tab(db, package):
    return Tab.objects.create(
        package=package,
        identifier="A",
        display_name="Tab A",
        order=1,
    )


@pytest.mark.django_db
class TestTabModel:
    def test_create_tab(self, package):
        tab = Tab.objects.create(
            package=package,
            identifier="A",
            display_name="Tab A",
            order=1,
        )
        assert tab.pk is not None
        assert tab.identifier == "A"
        assert tab.is_required is True

    def test_tab_identifier_immutable(self, package):
        tab = Tab.objects.create(
            package=package,
            identifier="A",
            display_name="Tab A",
            order=1,
        )
        tab.identifier = "B"
        tab.save()
        tab.refresh_from_db()
        assert tab.identifier == "A"

    def test_next_identifier_single_letter(self, package):
        assert Tab.get_next_identifier(package) == "A"
        Tab.objects.create(package=package, identifier="A", display_name="Tab A", order=1)
        assert Tab.get_next_identifier(package) == "B"

    def test_next_identifier_double_letter(self, package):
        for i, letter in enumerate("ABCDEFGHIJKLMNOPQRSTUVWXYZ"):
            Tab.objects.create(package=package, identifier=letter, display_name=f"Tab {letter}", order=i + 1)
        assert Tab.get_next_identifier(package) == "AA"


@pytest.mark.django_db
class TestDocumentModel:
    def test_create_document(self, tab, user):
        test_file = SimpleUploadedFile("test.pdf", b"PDF content here", content_type="application/pdf")
        doc = Document.objects.create(
            tab=tab,
            version=1,
            file=test_file,
            filename="test.pdf",
            file_size=len(b"PDF content here"),
            mime_type="application/pdf",
            uploaded_by=user,
        )
        assert doc.pk is not None
        assert doc.version == 1
        assert doc.is_current is True
        assert doc.sha256_hash

    def test_document_versioning(self, tab, user):
        file1 = SimpleUploadedFile("v1.pdf", b"Version 1", content_type="application/pdf")
        doc1 = Document.objects.create(
            tab=tab, version=1, file=file1, filename="doc.pdf",
            file_size=9, mime_type="application/pdf", uploaded_by=user, is_current=True,
        )
        file2 = SimpleUploadedFile("v2.pdf", b"Version 2", content_type="application/pdf")
        doc2 = Document.objects.create(
            tab=tab, version=2, file=file2, filename="doc.pdf",
            file_size=9, mime_type="application/pdf", uploaded_by=user, is_current=True,
        )
        doc1.refresh_from_db()
        assert doc1.is_current is False
        assert doc2.is_current is True


@pytest.fixture
def workflow_template(db, user, organization):
    return WorkflowTemplate.objects.create(
        organization=organization,
        name="Standard Review",
        description="Standard document review workflow",
        created_by=user,
    )


@pytest.mark.django_db
class TestWorkflowTemplateModel:
    def test_create_workflow_template(self, user, organization):
        """Test basic workflow template creation."""
        template = WorkflowTemplate.objects.create(
            organization=organization,
            name="Review Workflow",
            description="A review workflow",
            created_by=user,
        )
        assert template.pk is not None
        assert template.version == 1
        assert template.is_active is True
        assert template.canvas_data == {}

    def test_workflow_template_version_increments(self, workflow_template):
        """Test version increments on save."""
        assert workflow_template.version == 1
        workflow_template.name = "Updated Name"
        workflow_template.save()
        workflow_template.refresh_from_db()
        assert workflow_template.version == 2

    def test_workflow_template_str_with_organization(self, workflow_template):
        """Test string representation with organization."""
        assert "[TEST]" in str(workflow_template)
        assert "Standard Review" in str(workflow_template)
        assert "(v1)" in str(workflow_template)

    def test_workflow_template_str_shared(self, user):
        """Test string representation for shared template."""
        template = WorkflowTemplate.objects.create(
            organization=None,
            name="Shared Workflow",
            created_by=user,
        )
        assert "[Shared]" in str(template)
        assert "Shared Workflow" in str(template)

    def test_workflow_template_canvas_data(self, user, organization):
        """Test canvas_data stores JSON properly."""
        canvas_data = {
            "nodes": [{"id": "1", "type": "stage"}],
            "connections": [{"from": "1", "to": "2"}],
        }
        template = WorkflowTemplate.objects.create(
            organization=organization,
            name="Visual Workflow",
            canvas_data=canvas_data,
            created_by=user,
        )
        template.refresh_from_db()
        assert template.canvas_data == canvas_data


@pytest.mark.django_db
class TestStageNodeModel:
    def test_create_stage_node(self, workflow_template, office):
        """Test basic stage node creation."""
        stage = StageNode.objects.create(
            template=workflow_template,
            node_id="stage_1",
            name="Initial Approval",
            action_type=StageNode.ActionType.APPROVE,
        )
        assert stage.pk is not None
        assert stage.node_type == WorkflowNode.NodeType.STAGE
        assert stage.is_optional is False

    def test_stage_node_action_types(self, workflow_template):
        """Test all action types are valid."""
        action_types = ["APPROVE", "COORD", "CONCUR"]
        for i, action_type in enumerate(action_types):
            stage = StageNode.objects.create(
                template=workflow_template,
                node_id=f"stage_{i}",
                name=f"{action_type} Stage",
                action_type=action_type,
            )
            assert stage.action_type == action_type

    def test_stage_node_assigned_offices(self, workflow_template, office):
        """Test many-to-many office assignments."""
        stage = StageNode.objects.create(
            template=workflow_template,
            node_id="stage_1",
            name="Multi-Office Approval",
            action_type=StageNode.ActionType.APPROVE,
        )
        stage.assigned_offices.add(office)
        assert office in stage.assigned_offices.all()

    def test_stage_node_str(self, workflow_template):
        """Test string representation."""
        stage = StageNode.objects.create(
            template=workflow_template,
            node_id="stage_1",
            name="Approval Stage",
            action_type=StageNode.ActionType.APPROVE,
        )
        assert "Approval Stage" in str(stage)
        assert "Approve" in str(stage)

    def test_stage_node_unique_constraint(self, workflow_template):
        """Test unique constraint on template + node_id."""
        StageNode.objects.create(
            template=workflow_template,
            node_id="stage_1",
            name="Stage 1",
            action_type=StageNode.ActionType.APPROVE,
        )
        with pytest.raises(Exception):  # IntegrityError
            StageNode.objects.create(
                template=workflow_template,
                node_id="stage_1",
                name="Duplicate Stage",
                action_type=StageNode.ActionType.APPROVE,
            )

    def test_stage_node_escalation(self, workflow_template, office, organization):
        """Test escalation office assignment."""
        escalation_office = Office.objects.create(
            organization=organization,
            code="ESC",
            name="Escalation Office",
        )
        stage = StageNode.objects.create(
            template=workflow_template,
            node_id="stage_1",
            name="Timed Stage",
            action_type=StageNode.ActionType.APPROVE,
            timeout_days=5,
            escalation_office=escalation_office,
        )
        assert stage.timeout_days == 5
        assert stage.escalation_office == escalation_office


@pytest.mark.django_db
class TestActionNodeModel:
    def test_create_action_node(self, workflow_template):
        """Test basic action node creation."""
        action = ActionNode.objects.create(
            template=workflow_template,
            node_id="action_1",
            name="Send Notification",
            action_type=ActionNode.ActionType.SEND_ALERT,
        )
        assert action.pk is not None
        assert action.node_type == WorkflowNode.NodeType.ACTION
        assert action.execution_mode == ActionNode.ExecutionMode.INLINE

    def test_action_node_action_types(self, workflow_template):
        """Test all action types are valid."""
        action_types = ["send_alert", "send_email", "complete", "reject", "wait", "webhook"]
        for i, action_type in enumerate(action_types):
            action = ActionNode.objects.create(
                template=workflow_template,
                node_id=f"action_{i}",
                name=f"{action_type} Action",
                action_type=action_type,
            )
            assert action.action_type == action_type

    def test_action_node_execution_modes(self, workflow_template):
        """Test execution modes."""
        inline_action = ActionNode.objects.create(
            template=workflow_template,
            node_id="action_inline",
            name="Inline Action",
            action_type=ActionNode.ActionType.SEND_EMAIL,
            execution_mode=ActionNode.ExecutionMode.INLINE,
        )
        forked_action = ActionNode.objects.create(
            template=workflow_template,
            node_id="action_forked",
            name="Forked Action",
            action_type=ActionNode.ActionType.WEBHOOK,
            execution_mode=ActionNode.ExecutionMode.FORKED,
        )
        assert inline_action.execution_mode == "inline"
        assert forked_action.execution_mode == "forked"

    def test_action_node_str_inline(self, workflow_template):
        """Test string representation for inline mode."""
        action = ActionNode.objects.create(
            template=workflow_template,
            node_id="action_1",
            name="Complete Action",
            action_type=ActionNode.ActionType.COMPLETE,
            execution_mode=ActionNode.ExecutionMode.INLINE,
        )
        assert "->" in str(action)
        assert "Complete Workflow" in str(action)

    def test_action_node_str_forked(self, workflow_template):
        """Test string representation for forked mode."""
        action = ActionNode.objects.create(
            template=workflow_template,
            node_id="action_1",
            name="Parallel Action",
            action_type=ActionNode.ActionType.WEBHOOK,
            execution_mode=ActionNode.ExecutionMode.FORKED,
        )
        assert "||" in str(action)

    def test_action_node_config(self, workflow_template):
        """Test action_config stores JSON properly."""
        config = {
            "url": "https://api.example.com/webhook",
            "method": "POST",
            "headers": {"Authorization": "Bearer token"},
        }
        action = ActionNode.objects.create(
            template=workflow_template,
            node_id="action_webhook",
            name="API Webhook",
            action_type=ActionNode.ActionType.WEBHOOK,
            action_config=config,
        )
        action.refresh_from_db()
        assert action.action_config == config

    def test_action_node_unique_constraint(self, workflow_template):
        """Test unique constraint on template + node_id."""
        ActionNode.objects.create(
            template=workflow_template,
            node_id="action_1",
            name="Action 1",
            action_type=ActionNode.ActionType.SEND_ALERT,
        )
        with pytest.raises(Exception):  # IntegrityError
            ActionNode.objects.create(
                template=workflow_template,
                node_id="action_1",
                name="Duplicate Action",
                action_type=ActionNode.ActionType.SEND_EMAIL,
            )


@pytest.mark.django_db
class TestNodeConnectionModel:
    def test_create_node_connection(self, workflow_template):
        """Test basic node connection creation."""
        connection = NodeConnection.objects.create(
            template=workflow_template,
            from_node="stage_1",
            to_node="stage_2",
        )
        assert connection.pk is not None
        assert connection.connection_type == NodeConnection.ConnectionType.DEFAULT

    def test_connection_types(self, workflow_template):
        """Test all connection types."""
        default_conn = NodeConnection.objects.create(
            template=workflow_template,
            from_node="stage_1",
            to_node="stage_2",
            connection_type=NodeConnection.ConnectionType.DEFAULT,
        )
        return_conn = NodeConnection.objects.create(
            template=workflow_template,
            from_node="stage_2",
            to_node="stage_1",
            connection_type=NodeConnection.ConnectionType.RETURN,
        )
        reject_conn = NodeConnection.objects.create(
            template=workflow_template,
            from_node="stage_1",
            to_node="reject_action",
            connection_type=NodeConnection.ConnectionType.REJECT,
        )
        assert default_conn.connection_type == "default"
        assert return_conn.connection_type == "return"
        assert reject_conn.connection_type == "reject"

    def test_connection_str_default(self, workflow_template):
        """Test string representation for default path."""
        connection = NodeConnection.objects.create(
            template=workflow_template,
            from_node="stage_1",
            to_node="stage_2",
            connection_type=NodeConnection.ConnectionType.DEFAULT,
        )
        assert "->" in str(connection)
        assert "stage_1" in str(connection)
        assert "stage_2" in str(connection)

    def test_connection_str_return(self, workflow_template):
        """Test string representation for return path."""
        connection = NodeConnection.objects.create(
            template=workflow_template,
            from_node="stage_2",
            to_node="stage_1",
            connection_type=NodeConnection.ConnectionType.RETURN,
        )
        assert "<-" in str(connection)

    def test_connection_str_reject(self, workflow_template):
        """Test string representation for reject path."""
        connection = NodeConnection.objects.create(
            template=workflow_template,
            from_node="stage_1",
            to_node="reject_node",
            connection_type=NodeConnection.ConnectionType.REJECT,
        )
        assert "X>" in str(connection)

    def test_connection_unique_constraint(self, workflow_template):
        """Test unique constraint on template + from_node + to_node + connection_type."""
        NodeConnection.objects.create(
            template=workflow_template,
            from_node="stage_1",
            to_node="stage_2",
            connection_type=NodeConnection.ConnectionType.DEFAULT,
        )
        with pytest.raises(Exception):  # IntegrityError
            NodeConnection.objects.create(
                template=workflow_template,
                from_node="stage_1",
                to_node="stage_2",
                connection_type=NodeConnection.ConnectionType.DEFAULT,
            )

    def test_connection_same_nodes_different_types(self, workflow_template):
        """Test same nodes can have different connection types."""
        NodeConnection.objects.create(
            template=workflow_template,
            from_node="stage_1",
            to_node="stage_2",
            connection_type=NodeConnection.ConnectionType.DEFAULT,
        )
        # This should work - same nodes but different connection type
        reject_conn = NodeConnection.objects.create(
            template=workflow_template,
            from_node="stage_1",
            to_node="stage_2",
            connection_type=NodeConnection.ConnectionType.REJECT,
        )
        assert reject_conn.pk is not None
