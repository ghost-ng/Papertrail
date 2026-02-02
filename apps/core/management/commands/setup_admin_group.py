"""Management command to setup system admin group."""

from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand

from apps.accounts.models import User


class Command(BaseCommand):
    help = "Setup system_admins group with comprehensive permissions"

    def add_arguments(self, parser):
        parser.add_argument(
            "--add-user",
            type=str,
            help="Email of user to add to system_admins group",
        )

    def handle(self, *args, **options):
        # Create or get the system_admins group
        group, created = Group.objects.get_or_create(name="system_admins")

        if created:
            self.stdout.write(self.style.SUCCESS("Created system_admins group"))
        else:
            self.stdout.write("system_admins group already exists")

        # Add all permissions for key models
        models_to_manage = [
            ("accounts", "user"),
            ("organizations", "organization"),
            ("organizations", "office"),
            ("organizations", "organizationmembership"),
            ("organizations", "officemembership"),
            ("packages", "package"),
            ("packages", "workflowtemplate"),
            ("packages", "stagenode"),
            ("packages", "actionnode"),
            ("core", "auditlog"),
            ("core", "systemsetting"),
            ("collaboration", "comment"),
            ("collaboration", "notification"),
        ]

        permissions_added = 0
        for app_label, model in models_to_manage:
            try:
                content_type = ContentType.objects.get(
                    app_label=app_label,
                    model=model,
                )
                permissions = Permission.objects.filter(content_type=content_type)
                for perm in permissions:
                    if perm not in group.permissions.all():
                        group.permissions.add(perm)
                        permissions_added += 1
            except ContentType.DoesNotExist:
                self.stdout.write(
                    self.style.WARNING(f"ContentType not found: {app_label}.{model}")
                )

        self.stdout.write(
            self.style.SUCCESS(f"Added {permissions_added} permissions to system_admins")
        )

        # Add user if specified
        if options["add_user"]:
            try:
                user = User.objects.get(email=options["add_user"])
                user.groups.add(group)
                user.is_staff = True  # Grant staff access for Django admin
                user.save(update_fields=["is_staff"])
                self.stdout.write(
                    self.style.SUCCESS(f"Added {user.email} to system_admins group")
                )
            except User.DoesNotExist:
                self.stdout.write(
                    self.style.ERROR(f"User not found: {options['add_user']}")
                )
