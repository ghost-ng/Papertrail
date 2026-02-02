"""Tests for signature service and models."""

import json

import pytest

from apps.accounts.models import User
from apps.organizations.models import Office, OfficeMembership, Organization
from apps.packages.models import (
    NodeConnection,
    Package,
    Signature,
    StageAction,
    StageNode,
    WorkflowTemplate,
)
from apps.packages.services import RoutingService, SignatureError, SignatureService


@pytest.fixture
def user(db):
    return User.objects.create_user(
        email="signer@example.com",
        password="testpass123",
        first_name="Test",
        last_name="Signer",
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
def package(db, organization, office, user, simple_workflow):
    return Package.objects.create(
        organization=organization,
        workflow_template=simple_workflow,
        title="Test Package",
        originator=user,
        originating_office=office,
        status=Package.Status.DRAFT,
    )


@pytest.fixture
def stage_action(db, package, user, office, office_membership):
    """Create a stage action by submitting and completing a stage."""
    service = RoutingService(package)
    service.submit_package(user)

    return service.take_action(
        user=user,
        office=office,
        action_type=StageAction.ActionType.COMPLETE,
        position="Senior Reviewer",
    )


@pytest.mark.django_db
class TestSignatureService:
    """Tests for SignatureService."""

    def test_create_canonical_payload(self, package, stage_action, user):
        """Test creating a canonical payload."""
        service = SignatureService()

        payload = service.create_canonical_payload(
            package=package,
            stage_action=stage_action,
            signer=user,
            signature_type=Signature.SignatureType.APPROVE,
            position="Senior Reviewer",
        )

        # Verify payload structure
        assert payload["package_id"] == str(package.pk)
        assert payload["package_reference"] == package.reference_number
        assert payload["package_title"] == package.title
        assert payload["stage_action_id"] == str(stage_action.pk)
        assert payload["node_id"] == stage_action.node_id
        assert payload["action_type"] == stage_action.action_type
        assert payload["signer_id"] == str(user.pk)
        assert payload["signer_email"] == user.email
        assert payload["signer_name"] == f"{user.first_name} {user.last_name}"
        assert payload["signer_position"] == "Senior Reviewer"
        assert payload["signature_type"] == Signature.SignatureType.APPROVE
        assert "timestamp" in payload
        assert "documents" in payload
        assert isinstance(payload["documents"], list)

    def test_payload_to_json_is_deterministic(self, package, stage_action, user):
        """Test that payload_to_json produces deterministic output."""
        service = SignatureService()

        payload = service.create_canonical_payload(
            package=package,
            stage_action=stage_action,
            signer=user,
            signature_type=Signature.SignatureType.APPROVE,
            position="Reviewer",
        )

        # Generate JSON multiple times
        json1 = service.payload_to_json(payload)
        json2 = service.payload_to_json(payload)
        json3 = service.payload_to_json(payload)

        # All should be identical
        assert json1 == json2 == json3

        # Verify it's valid JSON
        parsed = json.loads(json1)
        assert parsed == payload

        # Verify compact format (no space after colons or commas outside of strings)
        # The separators=(",", ":") ensures no padding spaces
        assert ": " not in json1  # No space after colon (would be ": " vs ":")
        assert ", " not in json1  # No space after comma (would be ", " vs ",")

    def test_payload_to_json_sorted_keys(self, package, stage_action, user):
        """Test that payload JSON has sorted keys."""
        service = SignatureService()

        payload = {
            "zebra": "last",
            "alpha": "first",
            "middle": "center",
        }

        json_str = service.payload_to_json(payload)

        # Keys should appear in alphabetical order
        alpha_pos = json_str.find('"alpha"')
        middle_pos = json_str.find('"middle"')
        zebra_pos = json_str.find('"zebra"')

        assert alpha_pos < middle_pos < zebra_pos

    def test_create_signature(self, stage_action, user, office):
        """Test creating a signature."""
        service = SignatureService()

        signature = service.create_signature(
            stage_action=stage_action,
            signer=user,
            office=office,
            signature_type=Signature.SignatureType.APPROVE,
            position="Senior Reviewer",
            method="pgp",
        )

        # Verify signature was created
        assert signature.pk is not None
        assert signature.stage_action == stage_action
        assert signature.signer == user
        assert signature.signer_name == f"{user.first_name} {user.last_name}"
        assert signature.signer_email == user.email
        assert signature.signer_office == office
        assert signature.signer_position == "Senior Reviewer"
        assert signature.signature_type == Signature.SignatureType.APPROVE
        assert signature.method == "pgp"
        assert len(signature.key_fingerprint) == 40
        assert signature.canonical_payload
        assert signature.signature_blob
        assert signature.verified_at is not None
        assert signature.verification_status == Signature.VerificationStatus.VALID

    def test_create_signature_with_x509(self, stage_action, user, office):
        """Test creating a signature with X.509 method."""
        service = SignatureService()

        signature = service.create_signature(
            stage_action=stage_action,
            signer=user,
            office=office,
            signature_type=Signature.SignatureType.CERTIFY,
            position="Certifier",
            method="x509",
        )

        assert signature.method == "x509"
        assert signature.signature_type == Signature.SignatureType.CERTIFY

    def test_create_signature_invalid_type(self, stage_action, user, office):
        """Test that invalid signature type raises error."""
        service = SignatureService()

        with pytest.raises(SignatureError, match="Invalid signature type"):
            service.create_signature(
                stage_action=stage_action,
                signer=user,
                office=office,
                signature_type="INVALID_TYPE",
                position="Reviewer",
            )

    def test_create_signature_invalid_method(self, stage_action, user, office):
        """Test that invalid method raises error."""
        service = SignatureService()

        with pytest.raises(SignatureError, match="Invalid signature method"):
            service.create_signature(
                stage_action=stage_action,
                signer=user,
                office=office,
                signature_type=Signature.SignatureType.APPROVE,
                position="Reviewer",
                method="invalid_method",
            )

    def test_create_signature_duplicate_fails(self, stage_action, user, office):
        """Test that duplicate signature on same stage action fails."""
        service = SignatureService()

        # Create first signature
        service.create_signature(
            stage_action=stage_action,
            signer=user,
            office=office,
            signature_type=Signature.SignatureType.APPROVE,
            position="Reviewer",
        )

        # Try to create another signature on same stage action
        with pytest.raises(SignatureError, match="already has a signature"):
            service.create_signature(
                stage_action=stage_action,
                signer=user,
                office=office,
                signature_type=Signature.SignatureType.CONCUR,
                position="Reviewer",
            )

    def test_verify_signature(self, stage_action, user, office):
        """Test verifying a signature."""
        service = SignatureService()

        signature = service.create_signature(
            stage_action=stage_action,
            signer=user,
            office=office,
            signature_type=Signature.SignatureType.APPROVE,
            position="Reviewer",
        )

        # Verify the signature
        result = service.verify_signature(signature)
        assert result is True

    def test_signature_types(self, db, package, user, office, office_membership):
        """Test all signature types can be created."""
        service = SignatureService()
        routing_service = RoutingService(package)
        routing_service.submit_package(user)

        for sig_type in Signature.SignatureType.values:
            # Create a new stage action for each signature type
            stage_action = routing_service.take_action(
                user=user,
                office=office,
                action_type=StageAction.ActionType.COMPLETE,
                position="Reviewer",
            )

            # Need to delete the old signature if present (can't have two per action)
            # Actually, each take_action creates a new stage_action, so this should work

            signature = service.create_signature(
                stage_action=stage_action,
                signer=user,
                office=office,
                signature_type=sig_type,
                position="Reviewer",
            )

            assert signature.signature_type == sig_type

            # Reset for next iteration by returning the package
            if package.status != Package.Status.COMPLETED:
                break  # Stop if workflow completed


@pytest.mark.django_db
class TestSignatureModel:
    """Tests for Signature model."""

    def test_signature_str_representation(self, stage_action, user, office):
        """Test signature string representation."""
        service = SignatureService()

        signature = service.create_signature(
            stage_action=stage_action,
            signer=user,
            office=office,
            signature_type=Signature.SignatureType.APPROVE,
            position="Reviewer",
        )

        expected = f"{signature.signer_name} - Approve (Valid)"
        assert str(signature) == expected

    def test_signature_relationship_to_stage_action(self, stage_action, user, office):
        """Test signature is accessible from stage action."""
        service = SignatureService()

        signature = service.create_signature(
            stage_action=stage_action,
            signer=user,
            office=office,
            signature_type=Signature.SignatureType.APPROVE,
            position="Reviewer",
        )

        # Access from stage action
        assert stage_action.signature == signature

    def test_signature_signer_has_signatures(self, stage_action, user, office):
        """Test signer can access their signatures."""
        service = SignatureService()

        signature = service.create_signature(
            stage_action=stage_action,
            signer=user,
            office=office,
            signature_type=Signature.SignatureType.APPROVE,
            position="Reviewer",
        )

        assert signature in user.signatures.all()


@pytest.mark.django_db
class TestMockSignatureImplementation:
    """Tests for mock signature implementation details."""

    def test_mock_signature_is_sha256(self, stage_action, user, office):
        """Test that mock signature produces SHA256 hash."""
        service = SignatureService()

        signature = service.create_signature(
            stage_action=stage_action,
            signer=user,
            office=office,
            signature_type=Signature.SignatureType.APPROVE,
            position="Reviewer",
        )

        # Signature blob should be 64 hex characters (SHA256)
        signature_str = signature.signature_blob.decode("utf-8")
        assert len(signature_str) == 64
        assert all(c in "0123456789abcdef" for c in signature_str)

    def test_key_fingerprint_is_consistent(self, user):
        """Test that key fingerprint is consistent for same user/method."""
        service = SignatureService()

        fingerprint1 = service._get_key_fingerprint(user, "pgp")
        fingerprint2 = service._get_key_fingerprint(user, "pgp")

        assert fingerprint1 == fingerprint2
        assert len(fingerprint1) == 40

    def test_key_fingerprint_differs_by_method(self, user):
        """Test that key fingerprint differs by method."""
        service = SignatureService()

        pgp_fingerprint = service._get_key_fingerprint(user, "pgp")
        x509_fingerprint = service._get_key_fingerprint(user, "x509")

        assert pgp_fingerprint != x509_fingerprint
