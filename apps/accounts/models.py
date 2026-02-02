"""User model and related models."""

from django.contrib.auth.models import AbstractUser
from django.db import models

from apps.core.models import TimeStampedModel

from .managers import UserManager


class User(AbstractUser):
    """Custom user model using email as the primary identifier."""

    # Remove username field, use email instead
    username = None
    email = models.EmailField("email address", unique=True)

    # Authentication method
    AUTH_METHOD_PASSWORD = "password"
    AUTH_METHOD_PKI = "pki"
    AUTH_METHOD_CHOICES = [
        (AUTH_METHOD_PASSWORD, "Password"),
        (AUTH_METHOD_PKI, "PKI/CAC"),
    ]
    auth_method = models.CharField(
        max_length=20,
        choices=AUTH_METHOD_CHOICES,
        default=AUTH_METHOD_PASSWORD,
    )

    # PKI fields
    PKI_STATUS_PENDING = "pending_approval"
    PKI_STATUS_APPROVED = "approved"
    PKI_STATUS_REVOKED = "revoked"
    PKI_STATUS_CHOICES = [
        (PKI_STATUS_PENDING, "Pending Approval"),
        (PKI_STATUS_APPROVED, "Approved"),
        (PKI_STATUS_REVOKED, "Revoked"),
    ]
    pki_certificate = models.BinaryField(null=True, blank=True)
    pki_certificate_fingerprint = models.CharField(max_length=64, blank=True)
    pki_status = models.CharField(
        max_length=20,
        choices=PKI_STATUS_CHOICES,
        blank=True,
    )
    pki_approved_at = models.DateTimeField(null=True, blank=True)
    pki_approved_by = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="pki_approvals",
    )

    # PGP fields (for non-PKI users)
    pgp_public_key = models.TextField(blank=True)
    pgp_private_key_encrypted = models.BinaryField(null=True, blank=True)
    pgp_key_fingerprint = models.CharField(max_length=64, blank=True)
    pgp_key_created_at = models.DateTimeField(null=True, blank=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["first_name", "last_name"]

    objects = UserManager()

    class Meta:
        ordering = ["email"]
        indexes = [
            models.Index(fields=["email"]),
            models.Index(fields=["auth_method"]),
            models.Index(fields=["pki_status"]),
        ]

    def __str__(self):
        return self.email

    @property
    def full_name(self):
        """Return the user's full name."""
        return f"{self.first_name} {self.last_name}".strip() or self.email

    @property
    def is_pki_user(self):
        """Check if user authenticates via PKI."""
        return self.auth_method == self.AUTH_METHOD_PKI

    @property
    def has_valid_pki(self):
        """Check if user has approved PKI certificate."""
        return self.is_pki_user and self.pki_status == self.PKI_STATUS_APPROVED

    @property
    def has_signing_capability(self):
        """Check if user can sign documents (either PKI or PGP)."""
        if self.is_pki_user:
            return self.has_valid_pki
        return bool(self.pgp_public_key and self.pgp_private_key_encrypted)


class Delegation(TimeStampedModel):
    """Out-of-office delegation of workflow responsibilities."""

    delegator = models.ForeignKey(
        "User",
        on_delete=models.CASCADE,
        related_name="delegations_given",
    )
    delegate = models.ForeignKey(
        "User",
        on_delete=models.CASCADE,
        related_name="delegations_received",
    )
    start_date = models.DateField()
    end_date = models.DateField()

    # Scope
    all_offices = models.BooleanField(default=True)
    specific_offices = models.ManyToManyField(
        "organizations.Office",
        blank=True,
        related_name="delegations",
    )

    # Permissions delegated
    can_complete = models.BooleanField(default=True)
    can_return = models.BooleanField(default=True)
    can_sign = models.BooleanField(default=False)  # Usually not delegated

    is_active = models.BooleanField(default=True)
    reason = models.CharField(max_length=255, blank=True)  # "On vacation"

    class Meta:
        ordering = ["-start_date"]
        indexes = [
            models.Index(fields=["delegator", "is_active"]),
            models.Index(fields=["delegate", "is_active"]),
            models.Index(fields=["start_date", "end_date"]),
        ]

    def __str__(self):
        return f"{self.delegator.email} -> {self.delegate.email} ({self.start_date} to {self.end_date})"

    @property
    def is_currently_active(self):
        """Check if delegation is active for today."""
        from django.utils import timezone

        today = timezone.now().date()
        return self.is_active and self.start_date <= today <= self.end_date

    @classmethod
    def get_active_delegation(cls, delegator, office=None):
        """Get active delegation for a user, optionally filtered by office."""
        from django.utils import timezone

        today = timezone.now().date()

        delegations = cls.objects.filter(
            delegator=delegator,
            is_active=True,
            start_date__lte=today,
            end_date__gte=today,
        )

        if office:
            delegations = delegations.filter(
                models.Q(all_offices=True) | models.Q(specific_offices=office)
            )

        return delegations.first()
