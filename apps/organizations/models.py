"""Organization, Office, and Membership models."""

from django.conf import settings
from django.db import models

from apps.core.models import TimeStampedModel


class Organization(TimeStampedModel):
    """Organization model - top level of hierarchy."""

    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    contact_email = models.EmailField(blank=True, help_text="General contact email for this organization")
    contact_phone = models.CharField(max_length=30, blank=True, help_text="Contact phone number")
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["code"]

    def __str__(self):
        return f"{self.code} - {self.name}"

    def save(self, *args, **kwargs):
        """Ensure code is uppercase."""
        self.code = self.code.upper()
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        """Return URL to organization detail page."""
        from django.urls import reverse
        return reverse("organizations:organization_detail", kwargs={"pk": self.pk})


class Office(TimeStampedModel):
    """Office model - belongs to an organization with unlimited nesting."""

    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="offices",
    )
    code = models.CharField(max_length=20)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    contact_email = models.EmailField(blank=True, help_text="General contact email for this office")
    contact_phone = models.CharField(max_length=30, blank=True, help_text="Contact phone number")
    parent = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="children",
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["organization__code", "code"]
        unique_together = ["organization", "code"]
        indexes = [
            models.Index(fields=["organization", "code"]),
            models.Index(fields=["is_active"]),
            models.Index(fields=["parent"]),
        ]

    def __str__(self):
        return f"{self.organization.code} {self.code}"

    @property
    def display_name(self):
        """Return full display name with org code."""
        return f"{self.organization.code} {self.code} - {self.name}"

    def get_ancestors(self):
        """Return list of ancestor offices (parent, grandparent, etc.)."""
        ancestors = []
        current = self.parent
        while current:
            ancestors.append(current)
            current = current.parent
        return ancestors

    def get_descendants(self):
        """Return all descendant offices recursively."""
        descendants = []
        for child in self.children.all():
            descendants.append(child)
            descendants.extend(child.get_descendants())
        return descendants

    def get_depth(self):
        """Return nesting depth (0 for root offices)."""
        depth = 0
        current = self.parent
        while current:
            depth += 1
            current = current.parent
        return depth

    def get_absolute_url(self):
        """Return URL to office detail page."""
        from django.urls import reverse
        return reverse(
            "organizations:office_detail",
            kwargs={"org_pk": self.organization.pk, "pk": self.pk},
        )


class OrganizationMembership(TimeStampedModel):
    """
    Membership at the organization level.

    Roles:
    - org_manager: Full access to manage the organization, all offices, and members
    - org_member: Visibility access - can view packages from all offices in the org
                  (even without direct office membership). Does not grant workflow
                  participation; that requires OfficeMembership.
    """

    ROLE_MANAGER = "org_manager"
    ROLE_MEMBER = "org_member"
    ROLE_CHOICES = [
        (ROLE_MANAGER, "Organization Manager"),
        (ROLE_MEMBER, "Organization Member"),
    ]

    STATUS_PENDING = "pending"
    STATUS_APPROVED = "approved"
    STATUS_REJECTED = "rejected"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_APPROVED, "Approved"),
        (STATUS_REJECTED, "Rejected"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="organization_memberships",
    )
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=ROLE_MEMBER)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)

    requested_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="org_membership_reviews",
    )
    rejection_reason = models.TextField(blank=True)

    class Meta:
        unique_together = ["user", "organization"]
        ordering = ["-requested_at"]
        indexes = [
            models.Index(fields=["user"]),
            models.Index(fields=["organization"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self):
        return f"{self.user.email} - {self.organization.code} ({self.role})"

    @property
    def is_approved(self):
        """Check if membership is approved."""
        return self.status == self.STATUS_APPROVED

    @property
    def is_manager(self):
        """Check if user is an org manager."""
        return self.role == self.ROLE_MANAGER and self.is_approved


class OfficeMembership(TimeStampedModel):
    """
    Membership at the office level.

    Roles:
    - manager: Can manage office members and create sub-offices
    - member: Participates in workflows assigned to this office

    Status workflow allows membership requests with manager approval.
    """

    ROLE_MANAGER = "manager"
    ROLE_MEMBER = "member"
    ROLE_CHOICES = [
        (ROLE_MANAGER, "Manager"),
        (ROLE_MEMBER, "Member"),
    ]

    STATUS_PENDING = "pending"
    STATUS_APPROVED = "approved"
    STATUS_REJECTED = "rejected"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_APPROVED, "Approved"),
        (STATUS_REJECTED, "Rejected"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="office_memberships",
    )
    office = models.ForeignKey(
        Office,
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=ROLE_MEMBER)
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_APPROVED,  # Direct adds are approved immediately
    )
    joined_at = models.DateTimeField(auto_now_add=True)
    added_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="office_memberships_added",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="office_membership_reviews",
    )
    rejection_reason = models.TextField(blank=True)

    class Meta:
        unique_together = ["user", "office"]
        ordering = ["-joined_at"]
        indexes = [
            models.Index(fields=["user"]),
            models.Index(fields=["office"]),
            models.Index(fields=["role"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self):
        return f"{self.user.email} - {self.office} ({self.role})"

    @property
    def is_approved(self):
        """Check if membership is approved."""
        return self.status == self.STATUS_APPROVED

    @property
    def is_manager(self):
        """Check if user is an approved office manager."""
        return self.role == self.ROLE_MANAGER and self.is_approved
