"""Views for the admin dashboard app."""

import json

from django.contrib import messages
from django.contrib.auth.models import Group
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.views import View
from django.views.generic import DetailView, ListView, TemplateView

from apps.accounts.models import User
from apps.core.models import AuditLog, SystemSetting
from apps.organizations.models import Office, OfficeMembership, Organization, OrganizationMembership
from apps.organizations.services import HierarchyService, PermissionService
from apps.packages.models import Package, WorkflowTemplate

from .mixins import SystemAdminRequiredMixin


class AdminDashboardView(SystemAdminRequiredMixin, TemplateView):
    """Main admin dashboard with system statistics."""

    template_name = "admin_dashboard/index.html"

    def get_context_data(self, **kwargs):
        """Add system statistics to context."""
        context = super().get_context_data(**kwargs)

        # User statistics
        context["total_users"] = User.objects.count()
        context["active_users"] = User.objects.filter(is_active=True).count()
        # Pending memberships (both org and office)
        context["pending_org_memberships"] = OrganizationMembership.objects.filter(
            status=OrganizationMembership.STATUS_PENDING
        ).count()
        context["pending_office_memberships"] = OfficeMembership.objects.filter(
            status=OfficeMembership.STATUS_PENDING
        ).count()
        context["pending_memberships"] = (
            context["pending_org_memberships"] + context["pending_office_memberships"]
        )

        # Organization statistics
        context["total_organizations"] = Organization.objects.count()
        context["total_offices"] = Office.objects.count()

        # Package statistics
        context["total_packages"] = Package.objects.count()
        context["packages_in_routing"] = Package.objects.filter(
            status=Package.Status.IN_ROUTING
        ).count()
        context["packages_completed"] = Package.objects.filter(
            status=Package.Status.COMPLETED
        ).count()
        context["packages_draft"] = Package.objects.filter(status=Package.Status.DRAFT).count()

        # Workflow statistics
        context["total_workflows"] = WorkflowTemplate.objects.count()
        context["active_workflows"] = WorkflowTemplate.objects.filter(is_active=True).count()

        # Recent audit logs
        context["recent_audit_logs"] = AuditLog.objects.select_related("actor", "organization")[
            :10
        ]

        return context


class UserManagementView(SystemAdminRequiredMixin, ListView):
    """User management view with search functionality."""

    template_name = "admin_dashboard/users.html"
    model = User
    context_object_name = "users"
    paginate_by = 25

    def get_queryset(self):
        """Filter users based on search query."""
        queryset = User.objects.all().order_by("-date_joined")
        search_query = self.request.GET.get("q", "").strip()

        if search_query:
            queryset = queryset.filter(
                Q(email__icontains=search_query)
                | Q(first_name__icontains=search_query)
                | Q(last_name__icontains=search_query)
            )

        # Filter by status
        status_filter = self.request.GET.get("status", "")
        if status_filter == "active":
            queryset = queryset.filter(is_active=True)
        elif status_filter == "inactive":
            queryset = queryset.filter(is_active=False)
        elif status_filter == "staff":
            queryset = queryset.filter(is_staff=True)

        return queryset

    def get_context_data(self, **kwargs):
        """Add search query to context."""
        context = super().get_context_data(**kwargs)
        context["search_query"] = self.request.GET.get("q", "")
        context["status_filter"] = self.request.GET.get("status", "")
        context["groups"] = Group.objects.all()
        return context


class UserDetailView(SystemAdminRequiredMixin, DetailView):
    """User detail view with membership management."""

    template_name = "admin_dashboard/user_detail.html"
    model = User
    context_object_name = "user_obj"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.object
        context["org_memberships"] = user.organization_memberships.select_related("organization")
        context["office_memberships"] = user.office_memberships.select_related(
            "office", "office__organization"
        )
        context["groups"] = Group.objects.all()
        context["user_groups"] = user.groups.all()
        context["organizations"] = Organization.objects.filter(is_active=True)
        context["offices"] = Office.objects.filter(is_active=True).select_related("organization")
        return context

    def post(self, request, *args, **kwargs):
        """Handle user updates."""
        self.object = self.get_object()
        action = request.POST.get("action")

        if action == "toggle_active":
            self.object.is_active = not self.object.is_active
            self.object.save()
            status = "activated" if self.object.is_active else "deactivated"
            messages.success(request, f"User {status} successfully.")

        elif action == "toggle_staff":
            self.object.is_staff = not self.object.is_staff
            self.object.save()
            status = "granted" if self.object.is_staff else "revoked"
            messages.success(request, f"Staff status {status}.")

        elif action == "add_to_group":
            group_id = request.POST.get("group_id")
            if group_id:
                group = get_object_or_404(Group, pk=group_id)
                self.object.groups.add(group)
                messages.success(request, f"Added to group '{group.name}'.")

        elif action == "remove_from_group":
            group_id = request.POST.get("group_id")
            if group_id:
                group = get_object_or_404(Group, pk=group_id)
                self.object.groups.remove(group)
                messages.success(request, f"Removed from group '{group.name}'.")

        elif action == "add_to_org":
            org_id = request.POST.get("org_id")
            role = request.POST.get("role", OrganizationMembership.ROLE_MEMBER)
            if org_id:
                org = get_object_or_404(Organization, pk=org_id)
                membership, created = OrganizationMembership.objects.get_or_create(
                    user=self.object,
                    organization=org,
                    defaults={
                        "role": role,
                        "status": OrganizationMembership.STATUS_APPROVED,
                        "reviewed_by": request.user,
                        "reviewed_at": timezone.now(),
                    },
                )
                if not created:
                    membership.status = OrganizationMembership.STATUS_APPROVED
                    membership.role = role
                    membership.reviewed_by = request.user
                    membership.reviewed_at = timezone.now()
                    membership.save()
                messages.success(request, f"Added to organization '{org.code}'.")

        elif action == "add_to_office":
            office_id = request.POST.get("office_id")
            role = request.POST.get("role", OfficeMembership.ROLE_MEMBER)
            if office_id:
                office = get_object_or_404(Office, pk=office_id)
                membership, created = OfficeMembership.objects.get_or_create(
                    user=self.object,
                    office=office,
                    defaults={
                        "role": role,
                        "added_by": request.user,
                    },
                )
                if not created:
                    membership.role = role
                    membership.save()
                messages.success(request, f"Added to office '{office}'.")

        elif action == "remove_from_org":
            membership_id = request.POST.get("membership_id")
            if membership_id:
                OrganizationMembership.objects.filter(pk=membership_id).delete()
                messages.success(request, "Removed from organization.")

        elif action == "remove_from_office":
            membership_id = request.POST.get("membership_id")
            if membership_id:
                OfficeMembership.objects.filter(pk=membership_id).delete()
                messages.success(request, "Removed from office.")

        return redirect("admin_dashboard:user_detail", pk=self.object.pk)


class UserSearchAPIView(SystemAdminRequiredMixin, View):
    """AJAX endpoint for user search autocomplete."""

    def get(self, request, *args, **kwargs):
        query = request.GET.get("q", "").strip()
        if len(query) < 2:
            return JsonResponse({"users": []})

        users = User.objects.filter(
            Q(email__icontains=query)
            | Q(first_name__icontains=query)
            | Q(last_name__icontains=query)
        )[:10]

        return JsonResponse(
            {
                "users": [
                    {
                        "id": u.id,
                        "email": u.email,
                        "name": u.get_full_name() or u.email,
                        "display": f"{u.get_full_name()} ({u.email})" if u.get_full_name() else u.email,
                    }
                    for u in users
                ]
            }
        )


class OrganizationManagementView(SystemAdminRequiredMixin, ListView):
    """Organization management view."""

    template_name = "admin_dashboard/organizations.html"
    model = Organization
    context_object_name = "organizations"
    paginate_by = 25

    def get_queryset(self):
        queryset = Organization.objects.annotate(
            office_count=Count("offices"), member_count=Count("memberships")
        ).order_by("code")

        search = self.request.GET.get("q", "").strip()
        if search:
            queryset = queryset.filter(Q(code__icontains=search) | Q(name__icontains=search))

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["search_query"] = self.request.GET.get("q", "")
        return context

    def post(self, request, *args, **kwargs):
        """Handle organization creation."""
        action = request.POST.get("action")

        if action == "create_org":
            code = request.POST.get("code", "").strip().upper()
            name = request.POST.get("name", "").strip()
            description = request.POST.get("description", "").strip()

            if code and name:
                if Organization.objects.filter(code=code).exists():
                    messages.error(request, f"Organization with code '{code}' already exists.")
                else:
                    org = Organization.objects.create(
                        code=code,
                        name=name,
                        description=description,
                    )
                    messages.success(request, f"Organization '{code}' created successfully.")
                    return redirect("admin_dashboard:organization_detail", pk=org.pk)
            else:
                messages.error(request, "Code and name are required.")

        return redirect("admin_dashboard:organizations")


class OrganizationDetailView(SystemAdminRequiredMixin, DetailView):
    """Organization detail with members and offices."""

    template_name = "admin_dashboard/organization_detail.html"
    model = Organization
    context_object_name = "org"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        org = self.object
        context["offices"] = org.offices.all()
        context["memberships"] = org.memberships.select_related("user").order_by("-requested_at")
        context["pending_memberships"] = org.memberships.filter(
            status=OrganizationMembership.STATUS_PENDING
        )
        return context

    def post(self, request, *args, **kwargs):
        """Handle organization updates."""
        self.object = self.get_object()
        action = request.POST.get("action")

        if action == "toggle_active":
            self.object.is_active = not self.object.is_active
            self.object.save()
            status = "activated" if self.object.is_active else "deactivated"
            messages.success(request, f"Organization {status}.")

        elif action == "approve_membership":
            membership_id = request.POST.get("membership_id")
            if membership_id:
                membership = get_object_or_404(OrganizationMembership, pk=membership_id)
                membership.status = OrganizationMembership.STATUS_APPROVED
                membership.reviewed_by = request.user
                membership.reviewed_at = timezone.now()
                membership.save()
                messages.success(request, f"Approved {membership.user.email}.")

        elif action == "reject_membership":
            membership_id = request.POST.get("membership_id")
            reason = request.POST.get("reason", "")
            if membership_id:
                membership = get_object_or_404(OrganizationMembership, pk=membership_id)
                membership.status = OrganizationMembership.STATUS_REJECTED
                membership.reviewed_by = request.user
                membership.reviewed_at = timezone.now()
                membership.rejection_reason = reason
                membership.save()
                messages.success(request, f"Rejected {membership.user.email}.")

        elif action == "add_member":
            user_id = request.POST.get("user_id")
            role = request.POST.get("role", OrganizationMembership.ROLE_MEMBER)
            if user_id:
                user = get_object_or_404(User, pk=user_id)
                OrganizationMembership.objects.get_or_create(
                    user=user,
                    organization=self.object,
                    defaults={
                        "role": role,
                        "status": OrganizationMembership.STATUS_APPROVED,
                        "reviewed_by": request.user,
                        "reviewed_at": timezone.now(),
                    },
                )
                messages.success(request, f"Added {user.email} to organization.")

        elif action == "create_office":
            code = request.POST.get("code", "").strip().upper()
            name = request.POST.get("name", "").strip()
            description = request.POST.get("description", "").strip()
            parent_id = request.POST.get("parent_id", "").strip()

            if code and name:
                if Office.objects.filter(organization=self.object, code=code).exists():
                    messages.error(request, f"Office with code '{code}' already exists.")
                else:
                    parent = None
                    if parent_id:
                        parent = Office.objects.filter(pk=parent_id, organization=self.object).first()

                    office = Office.objects.create(
                        organization=self.object,
                        code=code,
                        name=name,
                        description=description,
                        parent=parent,
                    )
                    messages.success(request, f"Office '{self.object.code} {code}' created.")
                    return redirect("admin_dashboard:office_detail", pk=office.pk)
            else:
                messages.error(request, "Code and name are required.")

        elif action == "delete_organization":
            # Check for packages before deleting
            package_count = self.object.packages.count()
            if package_count > 0:
                messages.error(
                    request,
                    f"Cannot delete organization with {package_count} package(s). "
                    "Archive or delete the packages first."
                )
            else:
                org_code = self.object.code
                self.object.delete()
                messages.success(request, f"Organization '{org_code}' deleted.")
                return redirect("admin_dashboard:organizations")

        return redirect("admin_dashboard:organization_detail", pk=self.object.pk)


class OfficeManagementView(SystemAdminRequiredMixin, ListView):
    """Office management view."""

    template_name = "admin_dashboard/offices.html"
    model = Office
    context_object_name = "offices"
    paginate_by = 25

    def get_queryset(self):
        queryset = Office.objects.select_related("organization", "parent").annotate(
            member_count=Count("memberships")
        )

        search = self.request.GET.get("q", "").strip()
        if search:
            queryset = queryset.filter(
                Q(code__icontains=search)
                | Q(name__icontains=search)
                | Q(organization__code__icontains=search)
            )

        org_filter = self.request.GET.get("org", "")
        if org_filter:
            queryset = queryset.filter(organization_id=org_filter)

        status_filter = self.request.GET.get("status", "")
        if status_filter == "active":
            queryset = queryset.filter(is_active=True)
        elif status_filter == "inactive":
            queryset = queryset.filter(is_active=False)

        return queryset.order_by("organization__code", "code")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["search_query"] = self.request.GET.get("q", "")
        context["org_filter"] = self.request.GET.get("org", "")
        context["status_filter"] = self.request.GET.get("status", "")
        context["organizations"] = Organization.objects.filter(is_active=True)
        # All offices for parent selection
        context["all_offices"] = Office.objects.filter(is_active=True).select_related("organization")
        return context

    def post(self, request, *args, **kwargs):
        """Handle office creation."""
        action = request.POST.get("action")

        if action == "create_office":
            org_id = request.POST.get("organization_id")
            code = request.POST.get("code", "").strip().upper()
            name = request.POST.get("name", "").strip()
            description = request.POST.get("description", "").strip()
            parent_id = request.POST.get("parent_id", "").strip()

            if org_id and code and name:
                org = get_object_or_404(Organization, pk=org_id)

                if Office.objects.filter(organization=org, code=code).exists():
                    messages.error(request, f"Office with code '{code}' already exists in {org.code}.")
                else:
                    parent = None
                    if parent_id:
                        parent = Office.objects.filter(pk=parent_id, organization=org).first()

                    office = Office.objects.create(
                        organization=org,
                        code=code,
                        name=name,
                        description=description,
                        parent=parent,
                    )
                    messages.success(request, f"Office '{org.code} {code}' created successfully.")
                    return redirect("admin_dashboard:office_detail", pk=office.pk)
            else:
                messages.error(request, "Organization, code, and name are required.")

        return redirect("admin_dashboard:offices")


class OfficeDetailView(SystemAdminRequiredMixin, DetailView):
    """Office detail with members management."""

    template_name = "admin_dashboard/office_detail.html"
    model = Office
    context_object_name = "office"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        office = self.object
        context["memberships"] = office.memberships.select_related("user", "added_by").order_by("-joined_at")
        context["role_choices"] = OfficeMembership.ROLE_CHOICES
        # Sub-offices
        context["sub_offices"] = office.children.filter(is_active=True)
        context["parent_office"] = office.parent
        return context

    def post(self, request, *args, **kwargs):
        """Handle office updates."""
        self.object = self.get_object()
        action = request.POST.get("action")

        if action == "toggle_active":
            self.object.is_active = not self.object.is_active
            self.object.save()
            status = "activated" if self.object.is_active else "deactivated"
            messages.success(request, f"Office {status}.")

        elif action == "add_member":
            user_id = request.POST.get("user_id")
            role = request.POST.get("role", OfficeMembership.ROLE_MEMBER)
            if user_id:
                user = get_object_or_404(User, pk=user_id)
                OfficeMembership.objects.get_or_create(
                    user=user,
                    office=self.object,
                    defaults={
                        "role": role,
                        "added_by": request.user,
                    },
                )
                messages.success(request, f"Added {user.email} to office.")

        elif action == "create_sub_office":
            code = request.POST.get("code", "").strip().upper()
            name = request.POST.get("name", "").strip()
            description = request.POST.get("description", "").strip()
            if code and name:
                if Office.objects.filter(organization=self.object.organization, code=code).exists():
                    messages.error(request, f"Office with code '{code}' already exists in {self.object.organization.code}.")
                else:
                    sub_office = Office.objects.create(
                        organization=self.object.organization,
                        parent=self.object,
                        code=code,
                        name=name,
                        description=description,
                    )
                    messages.success(request, f"Created sub-office '{self.object.organization.code} {code}'.")
                    return redirect("admin_dashboard:office_detail", pk=sub_office.pk)
            else:
                messages.error(request, "Code and name are required.")

        elif action == "update_role":
            membership_id = request.POST.get("membership_id")
            role = request.POST.get("role")
            if membership_id and role:
                membership = get_object_or_404(OfficeMembership, pk=membership_id)
                membership.role = role
                membership.save()
                messages.success(request, f"Updated role for {membership.user.email}.")

        elif action == "remove_member":
            membership_id = request.POST.get("membership_id")
            if membership_id:
                OfficeMembership.objects.filter(pk=membership_id).delete()
                messages.success(request, "Removed member from office.")

        elif action == "delete_office":
            # Check for sub-offices
            sub_office_count = self.object.children.count()
            if sub_office_count > 0:
                messages.error(
                    request,
                    f"Cannot delete office with {sub_office_count} sub-office(s). "
                    "Delete sub-offices first."
                )
            # Check for packages originated from this office
            elif self.object.originated_packages.exists():
                messages.error(
                    request,
                    "Cannot delete office with originated packages. "
                    "Archive the packages first."
                )
            else:
                org_pk = self.object.organization.pk
                office_name = str(self.object)
                self.object.delete()
                messages.success(request, f"Office '{office_name}' deleted.")
                return redirect("admin_dashboard:organization_detail", pk=org_pk)

        return redirect("admin_dashboard:office_detail", pk=self.object.pk)


class WorkflowManagementView(SystemAdminRequiredMixin, ListView):
    """Workflow template management view."""

    template_name = "admin_dashboard/workflows.html"
    model = WorkflowTemplate
    context_object_name = "workflows"
    paginate_by = 25

    def get_queryset(self):
        queryset = WorkflowTemplate.objects.select_related("organization", "created_by").annotate(
            package_count=Count("packages")
        )

        search = self.request.GET.get("q", "").strip()
        if search:
            queryset = queryset.filter(Q(name__icontains=search) | Q(description__icontains=search))

        org_filter = self.request.GET.get("org", "")
        if org_filter:
            queryset = queryset.filter(organization_id=org_filter)

        status_filter = self.request.GET.get("status", "")
        if status_filter == "active":
            queryset = queryset.filter(is_active=True)
        elif status_filter == "inactive":
            queryset = queryset.filter(is_active=False)

        return queryset.order_by("-created_at")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["search_query"] = self.request.GET.get("q", "")
        context["org_filter"] = self.request.GET.get("org", "")
        context["status_filter"] = self.request.GET.get("status", "")
        context["organizations"] = Organization.objects.filter(is_active=True)
        return context


class AuditLogView(SystemAdminRequiredMixin, ListView):
    """Audit log viewer with filters."""

    template_name = "admin_dashboard/audit_log.html"
    model = AuditLog
    context_object_name = "audit_logs"
    paginate_by = 50

    def get_queryset(self):
        """Filter audit logs based on query parameters."""
        queryset = AuditLog.objects.select_related("actor", "organization")

        # Filter by action
        action = self.request.GET.get("action", "").strip()
        if action:
            queryset = queryset.filter(action=action)

        # Filter by resource type
        resource_type = self.request.GET.get("resource_type", "").strip()
        if resource_type:
            queryset = queryset.filter(resource_type=resource_type)

        # Filter by actor email
        actor_email = self.request.GET.get("actor_email", "").strip()
        if actor_email:
            queryset = queryset.filter(actor_email__icontains=actor_email)

        # Filter by organization
        org_filter = self.request.GET.get("org", "")
        if org_filter:
            queryset = queryset.filter(organization_id=org_filter)

        return queryset

    def get_context_data(self, **kwargs):
        """Add filter values to context."""
        context = super().get_context_data(**kwargs)
        context["action_filter"] = self.request.GET.get("action", "")
        context["resource_type_filter"] = self.request.GET.get("resource_type", "")
        context["actor_email_filter"] = self.request.GET.get("actor_email", "")
        context["org_filter"] = self.request.GET.get("org", "")

        # Get unique actions and resource types for filter dropdowns
        context["available_actions"] = (
            AuditLog.objects.values_list("action", flat=True).distinct().order_by("action")
        )
        context["available_resource_types"] = (
            AuditLog.objects.values_list("resource_type", flat=True)
            .distinct()
            .order_by("resource_type")
        )
        context["organizations"] = Organization.objects.all()

        return context


class SystemSettingsView(SystemAdminRequiredMixin, TemplateView):
    """System settings view and edit."""

    template_name = "admin_dashboard/settings.html"

    def get_context_data(self, **kwargs):
        """Add settings grouped by category to context."""
        context = super().get_context_data(**kwargs)

        settings = SystemSetting.objects.all()
        settings_by_category = {}

        for setting in settings:
            category = setting.category or "general"
            if category not in settings_by_category:
                settings_by_category[category] = []
            settings_by_category[category].append(setting)

        context["settings_by_category"] = settings_by_category
        context["groups"] = Group.objects.all()
        return context

    def post(self, request, *args, **kwargs):
        """Handle settings update."""
        import os
        from django.conf import settings as django_settings
        from django.core.files.storage import default_storage

        action = request.POST.get("action", "update_setting")

        if action == "upload_file":
            setting_key = request.POST.get("key")
            uploaded_file = request.FILES.get("file")

            if setting_key and uploaded_file:
                try:
                    setting = SystemSetting.objects.get(key=setting_key)

                    # Create branding directory if it doesn't exist
                    upload_dir = "branding"
                    file_ext = os.path.splitext(uploaded_file.name)[1].lower()
                    file_name = f"{setting_key}{file_ext}"
                    file_path = os.path.join(upload_dir, file_name)

                    # Delete old file if exists
                    if default_storage.exists(file_path):
                        default_storage.delete(file_path)

                    # Save the new file
                    saved_path = default_storage.save(file_path, uploaded_file)
                    file_url = f"{django_settings.MEDIA_URL}{saved_path}"

                    setting.value = file_url
                    setting.updated_by = request.user
                    setting.save()
                    messages.success(request, f"File uploaded for '{setting_key}'.")
                except SystemSetting.DoesNotExist:
                    messages.error(request, f"Setting '{setting_key}' not found.")

        elif action == "update_setting":
            setting_key = request.POST.get("key")
            setting_value = request.POST.get("value")

            if setting_key:
                try:
                    setting = SystemSetting.objects.get(key=setting_key)
                    try:
                        parsed_value = json.loads(setting_value)
                    except (json.JSONDecodeError, TypeError):
                        parsed_value = setting_value

                    setting.value = parsed_value
                    setting.updated_by = request.user
                    setting.save()
                    messages.success(request, f"Setting '{setting_key}' updated successfully.")
                except SystemSetting.DoesNotExist:
                    messages.error(request, f"Setting '{setting_key}' not found.")

        elif action == "create_setting":
            key = request.POST.get("key")
            value = request.POST.get("value")
            category = request.POST.get("category", "general")
            description = request.POST.get("description", "")

            if key:
                try:
                    parsed_value = json.loads(value)
                except (json.JSONDecodeError, TypeError):
                    parsed_value = value

                SystemSetting.objects.create(
                    key=key,
                    value=parsed_value,
                    category=category,
                    description=description,
                    updated_by=request.user,
                )
                messages.success(request, f"Setting '{key}' created.")

        elif action == "create_group":
            group_name = request.POST.get("group_name")
            if group_name:
                Group.objects.get_or_create(name=group_name)
                messages.success(request, f"Group '{group_name}' created.")

        return redirect("admin_dashboard:settings")


class PermissionHierarchyView(SystemAdminRequiredMixin, TemplateView):
    """Full permission hierarchy visualization with nested offices."""

    template_name = "admin_dashboard/hierarchy.html"

    def get_context_data(self, **kwargs):
        """Build the permission hierarchy tree."""
        context = super().get_context_data(**kwargs)

        # Get system admin group members
        try:
            system_admins_group = Group.objects.get(name="system_admins")
            context["system_admins"] = system_admins_group.user_set.filter(is_active=True)
        except Group.DoesNotExist:
            context["system_admins"] = User.objects.none()

        # Get all permission groups
        context["groups"] = Group.objects.annotate(
            member_count=Count("user")
        ).order_by("name")

        # Build organization hierarchy with nested offices
        organizations = Organization.objects.filter(is_active=True).annotate(
            member_count=Count("memberships", filter=Q(memberships__status="approved")),
            office_count=Count("offices", filter=Q(offices__is_active=True)),
        ).order_by("code")

        hierarchy = []
        for org in organizations:
            org_data = {
                "organization": org,
                "managers": OrganizationMembership.objects.filter(
                    organization=org,
                    role=OrganizationMembership.ROLE_MANAGER,
                    status="approved",
                ).select_related("user"),
                "offices": HierarchyService.build_nested_tree(org),
            }
            hierarchy.append(org_data)

        context["hierarchy"] = hierarchy

        # Statistics
        context["total_users"] = User.objects.filter(is_active=True).count()
        context["total_organizations"] = organizations.count()
        context["total_offices"] = Office.objects.filter(is_active=True).count()

        return context


class PendingApprovalsView(SystemAdminRequiredMixin, TemplateView):
    """View all pending membership approvals across the system."""

    template_name = "admin_dashboard/pending_approvals.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Pending organization memberships
        context["pending_org_memberships"] = OrganizationMembership.objects.filter(
            status=OrganizationMembership.STATUS_PENDING
        ).select_related("user", "organization").order_by("-requested_at")

        # Pending office memberships
        context["pending_office_memberships"] = OfficeMembership.objects.filter(
            status=OfficeMembership.STATUS_PENDING
        ).select_related("user", "office", "office__organization").order_by("-joined_at")

        return context

    def post(self, request, *args, **kwargs):
        """Handle batch approval/rejection."""
        action = request.POST.get("action")
        membership_type = request.POST.get("membership_type")
        membership_id = request.POST.get("membership_id")

        if membership_type == "org":
            membership = get_object_or_404(OrganizationMembership, pk=membership_id)
            if action == "approve":
                membership.status = OrganizationMembership.STATUS_APPROVED
                membership.reviewed_at = timezone.now()
                membership.reviewed_by = request.user
                membership.save()
                messages.success(request, f"Approved {membership.user.email} for {membership.organization.code}.")
            elif action == "reject":
                membership.status = OrganizationMembership.STATUS_REJECTED
                membership.reviewed_at = timezone.now()
                membership.reviewed_by = request.user
                membership.rejection_reason = request.POST.get("reason", "")
                membership.save()
                messages.success(request, f"Rejected {membership.user.email} for {membership.organization.code}.")

        elif membership_type == "office":
            membership = get_object_or_404(OfficeMembership, pk=membership_id)
            if action == "approve":
                membership.status = OfficeMembership.STATUS_APPROVED
                membership.reviewed_at = timezone.now()
                membership.reviewed_by = request.user
                membership.save()
                messages.success(request, f"Approved {membership.user.email} for {membership.office}.")
            elif action == "reject":
                membership.status = OfficeMembership.STATUS_REJECTED
                membership.reviewed_at = timezone.now()
                membership.reviewed_by = request.user
                membership.rejection_reason = request.POST.get("reason", "")
                membership.save()
                messages.success(request, f"Rejected {membership.user.email} for {membership.office}.")

        return redirect("admin_dashboard:pending_approvals")
