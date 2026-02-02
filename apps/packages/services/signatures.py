"""Signature service for cryptographic signing of stage actions."""

import hashlib
import json
from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.packages.models import Package, Signature, StageAction


class SignatureError(Exception):
    """Exception raised for signature-related errors."""

    pass


class SignatureService:
    """Service for creating and verifying cryptographic signatures."""

    def create_canonical_payload(
        self,
        package: Package,
        stage_action: StageAction,
        signer,
        signature_type: str,
        position: str,
    ) -> dict[str, Any]:
        """
        Create a canonical payload dictionary for signing.

        The payload contains all information needed to verify the signature
        was made for a specific action at a specific point in time.
        """
        # Get current document hashes for all tabs
        document_hashes = []
        for tab in package.tabs.all().order_by("order"):
            current_doc = tab.current_document
            if current_doc:
                document_hashes.append(
                    {
                        "tab_identifier": tab.identifier,
                        "tab_name": tab.display_name,
                        "document_version": current_doc.version,
                        "sha256_hash": current_doc.sha256_hash,
                    }
                )

        payload = {
            "package_id": str(package.pk),
            "package_reference": package.reference_number,
            "package_title": package.title,
            "stage_action_id": str(stage_action.pk),
            "node_id": stage_action.node_id,
            "action_type": stage_action.action_type,
            "signer_id": str(signer.pk),
            "signer_email": signer.email,
            "signer_name": f"{signer.first_name} {signer.last_name}".strip(),
            "signer_position": position,
            "signature_type": signature_type,
            "timestamp": timezone.now().isoformat(),
            "documents": document_hashes,
        }

        return payload

    def payload_to_json(self, payload: dict[str, Any]) -> str:
        """
        Convert payload to canonical JSON string.

        Uses sorted keys and no extra whitespace for deterministic output.
        """
        return json.dumps(payload, sort_keys=True, separators=(",", ":"))

    @transaction.atomic
    def create_signature(
        self,
        stage_action: StageAction,
        signer,
        office,
        signature_type: str,
        position: str,
        method: str = "pgp",
    ) -> Signature:
        """
        Create a signature for a stage action.

        Args:
            stage_action: The stage action being signed
            signer: The user signing
            office: The signer's office
            signature_type: Type of signature (CONCUR, APPROVE, etc.)
            position: Signer's position/title
            method: Cryptographic method (pgp or x509)

        Returns:
            The created Signature instance

        Raises:
            SignatureError: If signature creation fails
        """
        # Validate signature type
        valid_types = [choice[0] for choice in Signature.SignatureType.choices]
        if signature_type not in valid_types:
            raise SignatureError(f"Invalid signature type: {signature_type}")

        # Validate method
        valid_methods = [choice[0] for choice in Signature.Method.choices]
        if method not in valid_methods:
            raise SignatureError(f"Invalid signature method: {method}")

        # Check if stage action already has a signature
        if hasattr(stage_action, "signature"):
            raise SignatureError("Stage action already has a signature")

        # Create canonical payload
        payload = self.create_canonical_payload(
            package=stage_action.package,
            stage_action=stage_action,
            signer=signer,
            signature_type=signature_type,
            position=position,
        )
        payload_json = self.payload_to_json(payload)

        # Create mock signature (for MVP)
        signature_blob = self._create_mock_signature(payload_json, signer)

        # Get key fingerprint
        key_fingerprint = self._get_key_fingerprint(signer, method)

        # Create signature record
        signature = Signature.objects.create(
            stage_action=stage_action,
            signer=signer,
            signer_name=f"{signer.first_name} {signer.last_name}".strip() or signer.email,
            signer_email=signer.email,
            signer_office=office,
            signer_position=position,
            signature_type=signature_type,
            method=method,
            key_fingerprint=key_fingerprint,
            canonical_payload=payload_json,
            signature_blob=signature_blob,
            verified_at=timezone.now(),
            verification_status=Signature.VerificationStatus.VALID,
        )

        return signature

    def verify_signature(self, signature: Signature) -> bool:
        """
        Verify a signature.

        For MVP, this always returns True as we're using mock signatures.
        In production, this would verify the cryptographic signature against
        the canonical payload using the signer's public key.

        Args:
            signature: The signature to verify

        Returns:
            True if valid, False otherwise
        """
        # MVP: Always return True
        # In production, this would:
        # 1. Retrieve the signer's public key using the key_fingerprint
        # 2. Verify the signature_blob against the canonical_payload
        # 3. Check key validity (not expired, not revoked)
        return True

    def _create_mock_signature(self, payload_json: str, signer) -> bytes:
        """
        Create a mock signature using SHA-256.

        For MVP, we create a hash of the payload combined with the signer ID.
        In production, this would use actual cryptographic signing.

        Args:
            payload_json: The canonical JSON payload
            signer: The user signing

        Returns:
            The mock signature as bytes
        """
        # Combine payload with signer ID for uniqueness
        sign_input = f"{payload_json}:{signer.pk}"
        signature_hash = hashlib.sha256(sign_input.encode("utf-8")).hexdigest()
        return signature_hash.encode("utf-8")

    def _get_key_fingerprint(self, user, method: str) -> str:
        """
        Get the key fingerprint for a user.

        For MVP, generates a mock fingerprint based on user ID and method.
        In production, this would retrieve the actual key fingerprint from
        the user's stored cryptographic keys.

        Args:
            user: The user whose key fingerprint to get
            method: The cryptographic method (pgp or x509)

        Returns:
            The key fingerprint string
        """
        # MVP: Generate mock fingerprint
        # In production, this would look up the user's actual key
        fingerprint_input = f"{user.pk}:{method}:{user.email}"
        return hashlib.sha256(fingerprint_input.encode("utf-8")).hexdigest()[:40]
