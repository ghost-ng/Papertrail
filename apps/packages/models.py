"""Package, Tab, and Document models for document routing."""

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.models import TimeStampedModel
from apps.packages.utils import calculate_file_hash, get_upload_path


class Package(TimeStampedModel):
    """A routing package containing tabbed documents."""

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        IN_ROUTING = "in_routing", "In Routing"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"
        ON_HOLD = "on_hold", "On Hold"
        ARCHIVED = "archived", "Archived"

    class Priority(models.TextChoices):
        LOW = "low", "Low"
        NORMAL = "normal", "Normal"
        URGENT = "urgent", "Urgent"

    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.PROTECT,
        related_name="packages",
    )
    workflow_template = models.ForeignKey(
        "packages.WorkflowTemplate",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="packages",
    )
    title = models.CharField(max_length=255)
    reference_number = models.CharField(max_length=50, unique=True, editable=False)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
        db_index=True,
    )
    priority = models.CharField(
        max_length=20,
        choices=Priority.choices,
        default=Priority.NORMAL,
        db_index=True,
    )
    priority_deadline = models.DateTimeField(null=True, blank=True)
    originator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="originated_packages",
    )
    originating_office = models.ForeignKey(
        "organizations.Office",
        on_delete=models.PROTECT,
        related_name="originated_packages",
    )
    current_node = models.CharField(max_length=100, blank=True)
    integrity_violation = models.BooleanField(default=False)
    submitted_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    archived_at = models.DateTimeField(null=True, blank=True)
    archived_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="archived_packages",
    )
    archive_reason = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["organization", "status"]),
            models.Index(fields=["current_node"]),
            models.Index(fields=["originator"]),
            models.Index(fields=["reference_number"]),
            models.Index(fields=["submitted_at"]),
        ]

    def __str__(self):
        return f"{self.reference_number} - {self.title}"

    def save(self, *args, **kwargs):
        if not self.reference_number:
            self.reference_number = self._generate_reference_number()
        super().save(*args, **kwargs)

    def _generate_reference_number(self):
        """Generate sequential reference number: ORG-YEAR-NNNNN."""
        year = timezone.now().year
        prefix = f"{self.organization.code}-{year}-"

        # Get the highest sequence number for this org/year
        last_package = (
            Package.objects.filter(reference_number__startswith=prefix)
            .order_by("-reference_number")
            .first()
        )

        if last_package:
            last_seq = int(last_package.reference_number.split("-")[-1])
            next_seq = last_seq + 1
        else:
            next_seq = 1

        return f"{prefix}{next_seq:05d}"


class WorkflowTemplate(TimeStampedModel):
    """Workflow template defining routing flow for packages."""

    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="workflow_templates",
        help_text="Null for shared templates available to all organizations",
    )
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    canvas_data = models.JSONField(
        default=dict,
        blank=True,
        help_text="Drawflow export data for visual rendering",
    )
    is_active = models.BooleanField(default=True, db_index=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="created_workflow_templates",
    )
    version = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ["name"]
        indexes = [
            models.Index(fields=["organization", "is_active"]),
            models.Index(fields=["created_by"]),
        ]

    def __str__(self):
        org_prefix = f"[{self.organization.code}] " if self.organization else "[Shared] "
        return f"{org_prefix}{self.name} (v{self.version})"

    def save(self, *args, **kwargs):
        if self.pk:
            self.version += 1
        super().save(*args, **kwargs)


class WorkflowNode(TimeStampedModel):
    """Abstract base model for workflow nodes."""

    class NodeType(models.TextChoices):
        STAGE = "stage", "Stage"
        ACTION = "action", "Action"

    template = models.ForeignKey(
        WorkflowTemplate,
        on_delete=models.CASCADE,
        related_name="%(class)s_nodes",
    )
    node_id = models.CharField(max_length=50)
    name = models.CharField(max_length=200)
    node_type = models.CharField(max_length=20, choices=NodeType.choices)
    position_x = models.IntegerField(default=0)
    position_y = models.IntegerField(default=0)
    config = models.JSONField(default=dict, blank=True)

    class Meta:
        abstract = True

    def __str__(self):
        return f"{self.name} ({self.node_type})"


class StageNode(WorkflowNode):
    """A workflow stage requiring human action."""

    class ActionType(models.TextChoices):
        APPROVE = "APPROVE", "Approve"
        COORD = "COORD", "Coordinate"
        CONCUR = "CONCUR", "Concur"

    class MultiOfficeRule(models.TextChoices):
        ANY = "any", "Any (first completion advances)"
        ALL = "all", "All (all offices must complete)"

    action_type = models.CharField(max_length=20, choices=ActionType.choices)
    assigned_offices = models.ManyToManyField(
        "organizations.Office",
        related_name="assigned_stage_nodes",
        blank=True,
    )
    multi_office_rule = models.CharField(
        max_length=10,
        choices=MultiOfficeRule.choices,
        default=MultiOfficeRule.ANY,
        help_text="When multiple offices are assigned: 'any' advances on first completion, 'all' waits for all",
    )
    is_optional = models.BooleanField(default=False)
    timeout_days = models.PositiveIntegerField(null=True, blank=True)
    escalation_office = models.ForeignKey(
        "organizations.Office",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="escalation_stage_nodes",
    )

    class Meta:
        unique_together = [["template", "node_id"]]
        indexes = [models.Index(fields=["template", "action_type"])]

    def save(self, *args, **kwargs):
        self.node_type = WorkflowNode.NodeType.STAGE
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} ({self.get_action_type_display()})"


class ActionNode(WorkflowNode):
    """An automated action node in the workflow."""

    class ActionType(models.TextChoices):
        SEND_ALERT = "send_alert", "Send Alert"
        SEND_EMAIL = "send_email", "Send Email"
        COMPLETE = "complete", "Complete Workflow"
        REJECT = "reject", "Reject Workflow"
        WAIT = "wait", "Wait"
        WEBHOOK = "webhook", "Webhook"

    class ExecutionMode(models.TextChoices):
        INLINE = "inline", "Inline (Blocking)"
        FORKED = "forked", "Forked (Parallel)"

    action_type = models.CharField(max_length=20, choices=ActionType.choices)
    execution_mode = models.CharField(
        max_length=10,
        choices=ExecutionMode.choices,
        default=ExecutionMode.INLINE,
    )
    action_config = models.JSONField(default=dict, blank=True)

    class Meta:
        unique_together = [["template", "node_id"]]
        indexes = [models.Index(fields=["template", "action_type"])]

    def save(self, *args, **kwargs):
        self.node_type = WorkflowNode.NodeType.ACTION
        super().save(*args, **kwargs)

    def __str__(self):
        mode = "||" if self.execution_mode == "forked" else "->"
        return f"{self.name} {mode} ({self.get_action_type_display()})"


class NodeConnection(TimeStampedModel):
    """Connection between workflow nodes."""

    class ConnectionType(models.TextChoices):
        DEFAULT = "default", "Default Path"
        RETURN = "return", "Return Path"
        REJECT = "reject", "Reject Path"

    template = models.ForeignKey(
        WorkflowTemplate,
        on_delete=models.CASCADE,
        related_name="connections",
    )
    from_node = models.CharField(max_length=50)
    to_node = models.CharField(max_length=50)
    connection_type = models.CharField(
        max_length=20,
        choices=ConnectionType.choices,
        default=ConnectionType.DEFAULT,
    )

    class Meta:
        unique_together = [["template", "from_node", "to_node", "connection_type"]]
        indexes = [
            models.Index(fields=["template", "from_node"]),
            models.Index(fields=["template", "to_node"]),
        ]

    def __str__(self):
        symbols = {"default": "->", "return": "<-", "reject": "X>"}
        return f"{self.from_node} {symbols.get(self.connection_type, '->')} {self.to_node}"


class Tab(TimeStampedModel):
    """A tab within a package, containing documents."""

    package = models.ForeignKey(
        Package,
        on_delete=models.CASCADE,
        related_name="tabs",
    )
    identifier = models.CharField(max_length=10)  # A, B, ... AA, AB, etc.
    display_name = models.CharField(max_length=100)
    order = models.PositiveIntegerField()
    is_required = models.BooleanField(default=True)

    # Store original identifier to prevent modification
    _original_identifier = None

    class Meta:
        ordering = ["order"]
        unique_together = [["package", "identifier"]]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._original_identifier = self.identifier

    def __str__(self):
        return f"{self.identifier}: {self.display_name}"

    def save(self, *args, **kwargs):
        # Prevent identifier modification after initial save
        if self.pk and self._original_identifier:
            self.identifier = self._original_identifier
        super().save(*args, **kwargs)
        self._original_identifier = self.identifier

    @classmethod
    def get_next_identifier(cls, package):
        """Generate the next tab identifier (A-Z, then AA-AZ, BA-BZ, etc.)."""
        existing = set(package.tabs.values_list("identifier", flat=True))

        # Single letters first: A-Z
        for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
            if letter not in existing:
                return letter

        # Double letters: AA-ZZ
        for first in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
            for second in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
                identifier = f"{first}{second}"
                if identifier not in existing:
                    return identifier

        raise ValueError("Maximum number of tabs reached")


class Document(TimeStampedModel):
    """A versioned document within a tab."""

    tab = models.ForeignKey(
        Tab,
        on_delete=models.CASCADE,
        related_name="documents",
    )
    version = models.PositiveIntegerField()
    file = models.FileField(upload_to=get_upload_path)
    filename = models.CharField(max_length=255)
    file_size = models.PositiveIntegerField()  # bytes
    mime_type = models.CharField(max_length=100)
    sha256_hash = models.CharField(max_length=64, editable=False)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="uploaded_documents",
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)
    is_current = models.BooleanField(default=True)

    class Meta:
        ordering = ["-version"]
        unique_together = [["tab", "version"]]
        indexes = [
            models.Index(fields=["filename"]),
        ]

    def __str__(self):
        return f"{self.filename} (v{self.version})"

    def save(self, *args, **kwargs):
        if not self.sha256_hash and self.file:
            self.sha256_hash = calculate_file_hash(self.file)
        if self.is_current:
            Document.objects.filter(tab=self.tab, is_current=True).exclude(pk=self.pk).update(is_current=False)
        super().save(*args, **kwargs)

    @classmethod
    def get_next_version(cls, tab):
        """Get the next version number for a tab."""
        max_version = tab.documents.aggregate(models.Max("version"))["version__max"]
        return (max_version or 0) + 1


# Add property to Tab for convenience
Tab.add_to_class(
    "current_document",
    property(lambda self: self.documents.filter(is_current=True).first()),
)


class StageAction(TimeStampedModel):
    """Records an action taken at a workflow stage."""

    class ActionType(models.TextChoices):
        COMPLETE = "complete", "Complete"
        RETURN = "return", "Return"
        REJECT = "reject", "Reject"

    package = models.ForeignKey(
        "packages.Package",
        on_delete=models.CASCADE,
        related_name="stage_actions",
    )
    node_id = models.CharField(max_length=50)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="stage_actions",
    )
    actor_office = models.ForeignKey(
        "organizations.Office",
        on_delete=models.PROTECT,
        related_name="stage_actions",
    )
    actor_position = models.CharField(max_length=200, blank=True)
    action_type = models.CharField(max_length=20, choices=ActionType.choices)
    comment = models.TextField(blank=True)
    return_to_node = models.CharField(max_length=50, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["package", "node_id"]),
            models.Index(fields=["actor"]),
        ]

    def __str__(self):
        return f"{self.package.reference_number} - {self.get_action_type_display()} at {self.node_id}"


class StageCompletion(TimeStampedModel):
    """Tracks office completion for multi-office 'all' rule stages."""

    package = models.ForeignKey(
        "packages.Package",
        on_delete=models.CASCADE,
        related_name="stage_completions",
    )
    node_id = models.CharField(max_length=50)
    office = models.ForeignKey(
        "organizations.Office",
        on_delete=models.PROTECT,
        related_name="stage_completions",
    )
    completed_by = models.ForeignKey(
        StageAction,
        on_delete=models.CASCADE,
        related_name="stage_completion",
    )

    class Meta:
        unique_together = [["package", "node_id", "office"]]
        indexes = [
            models.Index(fields=["package", "node_id"]),
        ]

    def __str__(self):
        return f"{self.package.reference_number} - {self.office.code} completed {self.node_id}"


class Signature(TimeStampedModel):
    """Cryptographic signature for stage actions."""

    class SignatureType(models.TextChoices):
        CONCUR = "CONCUR", "Concur"
        APPROVE = "APPROVE", "Approve"
        CERTIFY = "CERTIFY", "Certify"
        ACKNOWLEDGE = "ACKNOWLEDGE", "Acknowledge"

    class Method(models.TextChoices):
        X509 = "x509", "X.509 Certificate"
        PGP = "pgp", "PGP Key"

    class VerificationStatus(models.TextChoices):
        VALID = "valid", "Valid"
        EXPIRED = "expired", "Expired"
        INVALID = "invalid", "Invalid"
        REVOKED = "revoked", "Revoked"

    stage_action = models.OneToOneField(
        StageAction,
        on_delete=models.CASCADE,
        related_name="signature",
    )
    signer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="signatures",
    )
    signer_name = models.CharField(max_length=255)
    signer_email = models.EmailField()
    signer_office = models.ForeignKey(
        "organizations.Office",
        on_delete=models.PROTECT,
        related_name="signatures",
    )
    signer_position = models.CharField(max_length=255)

    signature_type = models.CharField(max_length=20, choices=SignatureType.choices)
    method = models.CharField(max_length=10, choices=Method.choices)
    key_fingerprint = models.CharField(max_length=64)

    canonical_payload = models.TextField()  # JSON
    signature_blob = models.BinaryField()
    certificate_snapshot = models.BinaryField(null=True, blank=True)

    verified_at = models.DateTimeField(null=True, blank=True)
    verification_status = models.CharField(
        max_length=20,
        choices=VerificationStatus.choices,
        default=VerificationStatus.VALID,
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["signer"]),
            models.Index(fields=["verification_status"]),
        ]

    def __str__(self):
        return f"{self.signer_name} - {self.get_signature_type_display()} ({self.get_verification_status_display()})"


class IntegrityViolation(TimeStampedModel):
    """Records document changes after signatures exist."""

    class Resolution(models.TextChoices):
        PENDING = "pending", "Pending"
        ACKNOWLEDGED = "acknowledged", "Acknowledged"
        RESET = "reset", "Routing Reset"

    package = models.ForeignKey(
        Package,
        on_delete=models.CASCADE,
        related_name="integrity_violations",
    )
    detected_at = models.DateTimeField(auto_now_add=True)
    violating_document = models.ForeignKey(
        Document,
        on_delete=models.CASCADE,
        related_name="violations",
    )
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="caused_violations",
    )
    affected_signatures = models.ManyToManyField(
        Signature,
        related_name="violations",
    )

    change_reason = models.TextField()
    resolution = models.CharField(
        max_length=20,
        choices=Resolution.choices,
        default=Resolution.PENDING,
    )
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="resolved_violations",
    )
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-detected_at"]
        indexes = [
            models.Index(fields=["package", "resolution"]),
            models.Index(fields=["detected_at"]),
        ]

    def __str__(self):
        return f"{self.package.reference_number} - Violation on {self.violating_document.filename}"


class RoutingHistory(TimeStampedModel):
    """Tracks package movement through workflow nodes."""

    class TransitionType(models.TextChoices):
        SUBMIT = "submit", "Submitted to Routing"
        ADVANCE = "advance", "Advanced to Next Stage"
        RETURN = "return", "Returned to Previous Stage"
        REJECT = "reject", "Rejected"
        COMPLETE = "complete", "Workflow Completed"

    package = models.ForeignKey(
        "packages.Package",
        on_delete=models.CASCADE,
        related_name="routing_history",
    )
    from_node = models.CharField(max_length=50, blank=True)
    to_node = models.CharField(max_length=50)
    transition_type = models.CharField(max_length=20, choices=TransitionType.choices)
    triggered_by = models.ForeignKey(
        StageAction,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="routing_transitions",
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name_plural = "Routing histories"
        indexes = [
            models.Index(fields=["package", "-created_at"]),
        ]

    def __str__(self):
        if self.from_node:
            return f"{self.package.reference_number}: {self.from_node} -> {self.to_node}"
        return f"{self.package.reference_number}: -> {self.to_node} ({self.get_transition_type_display()})"
