"""Views for package management."""

import json

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.generic import ListView, DetailView, CreateView, UpdateView, View
from django.http import FileResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator

from apps.core.mixins import AuditLogMixin
from apps.organizations.models import OrganizationMembership, OfficeMembership, Organization, Office
from apps.packages.forms import (
    PackageForm, TabForm, DocumentUploadForm, WorkflowTemplateForm, StageActionForm,
    PackageStageAssignmentForm, PackageActionRecipientForm
)
from apps.packages.models import (
    Package, Tab, Document, WorkflowTemplate, StageNode, ActionNode, NodeConnection,
    PackageStageAssignment, PackageActionRecipient
)
from apps.packages.services import RoutingService, RoutingError


class PackageAccessMixin:
    """
    Mixin for package access control.

    Visibility rules:
    - Superusers: Can see all packages
    - org_member/org_manager: Can see all packages from their organization
    - office_member: Can see packages from their office(s)
    - Package originator: Can always see their own packages
    """

    def get_user_organizations(self):
        """Get organizations where user has approved membership (visibility access)."""
        if self.request.user.is_superuser:
            return Organization.objects.values_list("id", flat=True)
        return OrganizationMembership.objects.filter(
            user=self.request.user, status="approved"
        ).values_list("organization_id", flat=True)

    def get_user_offices(self):
        # Superusers can access all offices
        if self.request.user.is_superuser:
            return Office.objects.values_list("id", flat=True)
        # Filter by approved memberships
        return OfficeMembership.objects.filter(
            user=self.request.user,
            status=OfficeMembership.STATUS_APPROVED,
        ).values_list("office_id", flat=True)

    def get_offices_for_initiation(self):
        """
        Get offices where user can create packages.

        Any approved office member can initiate packages from their offices.
        Workflow assignment determines what actions they can take.
        """
        if self.request.user.is_superuser:
            return Office.objects.filter(is_active=True)
        # Get user's approved office memberships
        user_office_ids = OfficeMembership.objects.filter(
            user=self.request.user,
            status=OfficeMembership.STATUS_APPROVED,
        ).values_list("office_id", flat=True)
        return Office.objects.filter(pk__in=user_office_ids, is_active=True)


class PackageListView(LoginRequiredMixin, PackageAccessMixin, ListView):
    model = Package
    template_name = "packages/package_list.html"
    context_object_name = "packages"
    paginate_by = 25

    def get_queryset(self):
        user_orgs = self.get_user_organizations()
        user_offices = self.get_user_offices()
        return Package.objects.filter(
            Q(organization_id__in=user_orgs) | Q(originator=self.request.user) | Q(originating_office_id__in=user_offices)
        ).select_related("organization", "originator", "originating_office").distinct()


class PackageDetailView(LoginRequiredMixin, PackageAccessMixin, DetailView):
    model = Package
    template_name = "packages/package_detail.html"
    context_object_name = "package"

    def get_queryset(self):
        user_orgs = self.get_user_organizations()
        user_offices = self.get_user_offices()
        return Package.objects.filter(
            Q(organization_id__in=user_orgs) | Q(originator=self.request.user) | Q(originating_office_id__in=user_offices)
        ).select_related("organization", "originator", "originating_office", "workflow_template").prefetch_related("tabs__documents")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        package = self.object
        user = self.request.user

        # Check if user can manage this package (pause/cancel/priority)
        context["can_manage"] = self._can_manage_package(user, package)

        # Add current time for template comparisons (suspense date)
        from django.utils import timezone as tz
        context["now"] = tz.now()

        # Get all workflow stages for overview with their assigned offices
        if package.workflow_template:
            stages = StageNode.objects.filter(
                template=package.workflow_template
            ).prefetch_related("assigned_offices").order_by("position_y", "position_x")

            # Attach package-specific office assignments to each stage
            stage_assignments = {
                sa.stage_id: sa
                for sa in PackageStageAssignment.objects.filter(
                    package=package
                ).prefetch_related("offices")
            }

            stages_with_assignments = []
            for stage in stages:
                if stage.id in stage_assignments:
                    stage.display_offices = stage_assignments[stage.id].offices.all()
                else:
                    stage.display_offices = stage.assigned_offices.all()
                stages_with_assignments.append(stage)

            context["workflow_stages"] = stages_with_assignments

        # Add routing context if in routing or on hold
        if package.status in [Package.Status.IN_ROUTING, Package.Status.ON_HOLD] and package.workflow_template:
            service = RoutingService(package)
            context["current_stage"] = service.get_current_stage()

            # Check if user can act (only if in routing, not on hold)
            stage = context["current_stage"]
            if stage and package.status == Package.Status.IN_ROUTING:
                user_offices = OfficeMembership.objects.filter(
                    user=self.request.user,
                    status=OfficeMembership.STATUS_APPROVED,
                ).values_list("office_id", flat=True)
                # Use package-specific assignment if available
                assigned_offices = service.get_offices_for_stage(stage)
                context["can_act"] = assigned_offices.filter(pk__in=user_offices).exists()
            else:
                context["can_act"] = False

        return context

    def _can_manage_package(self, user, package):
        """Check if user can manage (pause/cancel/priority) this package."""
        if user.is_superuser:
            return True
        if package.originator == user:
            return True
        # Org manager check
        if OrganizationMembership.objects.filter(
            user=user,
            organization=package.organization,
            role=OrganizationMembership.ROLE_MANAGER,
            status=OrganizationMembership.STATUS_APPROVED,
        ).exists():
            return True
        # Originating office manager check
        if OfficeMembership.objects.filter(
            user=user,
            office=package.originating_office,
            role=OfficeMembership.ROLE_MANAGER,
            status=OfficeMembership.STATUS_APPROVED,
        ).exists():
            return True
        return False


class PackageCreateView(LoginRequiredMixin, PackageAccessMixin, CreateView):
    model = Package
    form_class = PackageForm
    template_name = "packages/package_form.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["organizations"] = OrganizationMembership.objects.filter(
            user=self.request.user, status="approved"
        ).select_related("organization")
        # Get offices where user can initiate packages (any role, office must have can_initiate)
        context["initiating_offices"] = self.get_offices_for_initiation().select_related("organization")
        return context

    def form_valid(self, form):
        form.instance.originator = self.request.user
        org_id = self.request.POST.get("organization")
        office_id = self.request.POST.get("originating_office")
        if org_id:
            form.instance.organization = get_object_or_404(Organization, pk=org_id)
        if office_id:
            # Verify user can initiate from this office
            office = get_object_or_404(Office, pk=office_id)
            allowed_offices = self.get_offices_for_initiation()
            if not self.request.user.is_superuser and office not in allowed_offices:
                messages.error(self.request, "You cannot initiate packages from this office.")
                return self.form_invalid(form)
            form.instance.originating_office = office
        response = super().form_valid(form)
        messages.success(self.request, f"Package {self.object.reference_number} created.")
        return response

    def get_success_url(self):
        return reverse("packages:package_detail", args=[self.object.pk])


class PackageUpdateView(LoginRequiredMixin, UpdateView):
    model = Package
    form_class = PackageForm
    template_name = "packages/package_form.html"

    def get_queryset(self):
        return Package.objects.filter(originator=self.request.user, status="draft")

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, "Package updated.")
        return response

    def get_success_url(self):
        return reverse("packages:package_detail", args=[self.object.pk])


class TabCreateView(LoginRequiredMixin, CreateView):
    model = Tab
    form_class = TabForm
    template_name = "packages/tab_form.html"

    def dispatch(self, request, *args, **kwargs):
        self.package = get_object_or_404(Package, pk=kwargs["package_pk"])
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["package"] = self.package
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["package"] = self.package
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, f"Tab {self.object.identifier} created.")
        return response

    def get_success_url(self):
        return reverse("packages:package_detail", args=[self.package.pk])


class TabUpdateView(LoginRequiredMixin, UpdateView):
    model = Tab
    form_class = TabForm
    template_name = "packages/tab_form.html"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["package"] = self.object.package
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["package"] = self.object.package
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, "Tab updated.")
        return response

    def get_success_url(self):
        return reverse("packages:package_detail", args=[self.object.package.pk])


class DocumentUploadView(LoginRequiredMixin, View):
    def _check_upload_allowed(self, package):
        """Check if document uploads are allowed at the current stage.

        Returns (allowed, error_message) tuple.
        """
        if package.status != Package.Status.IN_ROUTING:
            return True, None

        # Get current stage
        service = RoutingService(package)
        current_stage = service.get_current_stage()

        if current_stage and current_stage.action_type in [
            StageNode.ActionType.COORD,
            StageNode.ActionType.CONCUR,
        ]:
            return False, (
                f"Document uploads are not allowed during {current_stage.get_action_type_display()} stages. "
                "The package must be returned for revision before documents can be modified."
            )

        return True, None

    def get(self, request, tab_pk):
        tab = get_object_or_404(Tab, pk=tab_pk)

        # Check if uploads are allowed
        allowed, error_msg = self._check_upload_allowed(tab.package)
        if not allowed:
            messages.error(request, error_msg)
            return redirect("packages:package_detail", pk=tab.package.pk)

        form = DocumentUploadForm(tab=tab)
        return render(request, "packages/document_upload.html", {"tab": tab, "package": tab.package, "form": form})

    def post(self, request, tab_pk):
        tab = get_object_or_404(Tab, pk=tab_pk)

        # Check if uploads are allowed
        allowed, error_msg = self._check_upload_allowed(tab.package)
        if not allowed:
            messages.error(request, error_msg)
            return redirect("packages:package_detail", pk=tab.package.pk)

        form = DocumentUploadForm(request.POST, request.FILES, tab=tab)
        if form.is_valid():
            document = form.save(uploaded_by=request.user)
            messages.success(request, f"Document '{document.filename}' uploaded (v{document.version}).")
            return redirect("packages:package_detail", pk=tab.package.pk)
        return render(request, "packages/document_upload.html", {"tab": tab, "package": tab.package, "form": form})


class DocumentDownloadView(LoginRequiredMixin, View):
    def get(self, request, pk):
        document = get_object_or_404(Document, pk=pk)
        return FileResponse(document.file.open("rb"), as_attachment=True, filename=document.filename)


# ============================================================================
# Workflow Views
# ============================================================================

class WorkflowAccessMixin:
    """Mixin for workflow access control."""

    def get_user_organizations(self):
        # Superusers can access all organizations
        if self.request.user.is_superuser:
            return Organization.objects.values_list("id", flat=True)
        return OrganizationMembership.objects.filter(
            user=self.request.user, status="approved"
        ).values_list("organization_id", flat=True)


class WorkflowTemplateListView(LoginRequiredMixin, WorkflowAccessMixin, ListView):
    """List workflow templates accessible to the user."""
    model = WorkflowTemplate
    template_name = "packages/workflow_list.html"
    context_object_name = "workflows"
    paginate_by = 25

    def get_queryset(self):
        user_orgs = self.get_user_organizations()
        # Show shared workflows (org=None) and organization-specific workflows
        return WorkflowTemplate.objects.filter(
            Q(organization__isnull=True) | Q(organization_id__in=user_orgs)
        ).select_related("organization", "created_by").order_by("-created_at")


class WorkflowTemplateCreateView(LoginRequiredMixin, WorkflowAccessMixin, CreateView):
    """Create a new workflow template."""
    model = WorkflowTemplate
    form_class = WorkflowTemplateForm
    template_name = "packages/workflow_form.html"

    def dispatch(self, request, *args, **kwargs):
        from apps.organizations.services import PermissionService
        if not PermissionService.can_create_workflow(request.user):
            messages.error(request, "You don't have permission to create workflow templates.")
            return redirect("packages:workflow_list")
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user_orgs = self.get_user_organizations()
        context["organizations"] = Organization.objects.filter(id__in=user_orgs)
        return context

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        response = super().form_valid(form)
        messages.success(self.request, f"Workflow '{self.object.name}' created. Now design the workflow in the builder.")
        return response

    def get_success_url(self):
        return reverse("packages:workflow_builder", args=[self.object.pk])


class WorkflowBuilderView(LoginRequiredMixin, WorkflowAccessMixin, DetailView):
    """Visual workflow builder using Drawflow."""
    model = WorkflowTemplate
    template_name = "packages/workflow_builder.html"
    context_object_name = "workflow"

    def get_queryset(self):
        user_orgs = self.get_user_organizations()
        return WorkflowTemplate.objects.filter(
            Q(organization__isnull=True) | Q(organization_id__in=user_orgs)
        ).select_related("organization")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Stage action types for toolbar
        context["stage_action_types"] = [
            {"value": choice[0], "label": choice[1]}
            for choice in StageNode.ActionType.choices
        ]

        # Action types for toolbar
        context["action_types"] = [
            {"value": choice[0], "label": choice[1]}
            for choice in ActionNode.ActionType.choices
        ]

        # Offices for the workflow's organization
        if self.object.organization:
            context["offices"] = Office.objects.filter(
                organization=self.object.organization
            ).values("id", "name", "code")
        else:
            # For shared workflows, provide all offices grouped by organization
            context["offices"] = Office.objects.select_related("organization").values(
                "id", "name", "code", "organization__name"
            )

        # Execution modes
        context["execution_modes"] = [
            {"value": choice[0], "label": choice[1]}
            for choice in ActionNode.ExecutionMode.choices
        ]

        # Connection types
        context["connection_types"] = [
            {"value": choice[0], "label": choice[1]}
            for choice in NodeConnection.ConnectionType.choices
        ]

        return context


@method_decorator(csrf_exempt, name="dispatch")
class WorkflowSaveAPIView(LoginRequiredMixin, View):
    """API endpoint to save workflow canvas data, nodes, and connections."""

    def post(self, request, pk):
        try:
            workflow = get_object_or_404(WorkflowTemplate, pk=pk)
            data = json.loads(request.body)

            # Handle rename-only requests
            if data.get("rename_only"):
                new_name = data.get("name", "").strip()
                if new_name:
                    workflow.name = new_name
                    workflow.save(update_fields=["name"])
                    return JsonResponse({"status": "success", "name": workflow.name})
                else:
                    return JsonResponse({"status": "error", "message": "Name cannot be empty"})

            # Save canvas data (Drawflow export)
            workflow.canvas_data = data.get("canvas_data", {})
            workflow.save()

            # Clear existing nodes and connections
            workflow.stagenode_nodes.all().delete()
            workflow.actionnode_nodes.all().delete()
            workflow.connections.all().delete()

            # Create nodes from canvas data
            node_mapping = {}  # Maps Drawflow node IDs to our node IDs
            for node_data in data.get("nodes", []):
                node_type = node_data.get("node_type")
                drawflow_id = node_data.get("drawflow_id")

                if node_type == "stage":
                    node = StageNode.objects.create(
                        template=workflow,
                        node_id=node_data.get("node_id", f"stage_{drawflow_id}"),
                        name=node_data.get("name", "Unnamed Stage"),
                        action_type=node_data.get("action_type", StageNode.ActionType.APPROVE),
                        multi_office_rule=node_data.get("multi_office_rule", StageNode.MultiOfficeRule.ANY),
                        is_optional=node_data.get("is_optional", False),
                        timeout_days=node_data.get("timeout_days"),
                        position_x=node_data.get("position_x", 0),
                        position_y=node_data.get("position_y", 0),
                        config=node_data.get("config", {}),
                    )
                    # Handle escalation office
                    escalation_office_id = node_data.get("escalation_office_id")
                    if escalation_office_id:
                        node.escalation_office_id = escalation_office_id
                        node.save()

                    # Handle assigned offices (M2M)
                    assigned_office_ids = node_data.get("assigned_office_ids", [])
                    if assigned_office_ids:
                        node.assigned_offices.set(assigned_office_ids)

                    node_mapping[drawflow_id] = node.node_id

                elif node_type == "action":
                    node = ActionNode.objects.create(
                        template=workflow,
                        node_id=node_data.get("node_id", f"action_{drawflow_id}"),
                        name=node_data.get("name", "Unnamed Action"),
                        action_type=node_data.get("action_type", ActionNode.ActionType.SEND_ALERT),
                        execution_mode=node_data.get("execution_mode", ActionNode.ExecutionMode.INLINE),
                        action_config=node_data.get("action_config", {}),
                        position_x=node_data.get("position_x", 0),
                        position_y=node_data.get("position_y", 0),
                        config=node_data.get("config", {}),
                    )
                    node_mapping[drawflow_id] = node.node_id

            # Create connections
            for conn_data in data.get("connections", []):
                from_drawflow_id = conn_data.get("from_node")
                to_drawflow_id = conn_data.get("to_node")

                # Map Drawflow IDs to our node IDs
                from_node_id = node_mapping.get(from_drawflow_id, conn_data.get("from_node_id"))
                to_node_id = node_mapping.get(to_drawflow_id, conn_data.get("to_node_id"))

                if from_node_id and to_node_id:
                    NodeConnection.objects.create(
                        template=workflow,
                        from_node=from_node_id,
                        to_node=to_node_id,
                        connection_type=conn_data.get("connection_type", NodeConnection.ConnectionType.DEFAULT),
                    )

            return JsonResponse({
                "status": "success",
                "version": workflow.version,
                "message": "Workflow saved successfully"
            })

        except json.JSONDecodeError:
            return JsonResponse({"status": "error", "message": "Invalid JSON"}, status=400)
        except Exception as e:
            return JsonResponse({"status": "error", "message": str(e)}, status=500)


class WorkflowLoadAPIView(LoginRequiredMixin, View):
    """API endpoint to load workflow canvas data, nodes, and connections."""

    def get(self, request, pk):
        workflow = get_object_or_404(WorkflowTemplate, pk=pk)

        # Build nodes list
        nodes = []

        # Stage nodes
        for stage in workflow.stagenode_nodes.all().prefetch_related("assigned_offices"):
            nodes.append({
                "node_type": "stage",
                "node_id": stage.node_id,
                "name": stage.name,
                "action_type": stage.action_type,
                "multi_office_rule": stage.multi_office_rule,
                "is_optional": stage.is_optional,
                "timeout_days": stage.timeout_days,
                "escalation_office_id": stage.escalation_office_id,
                "assigned_office_ids": list(stage.assigned_offices.values_list("id", flat=True)),
                "position_x": stage.position_x,
                "position_y": stage.position_y,
                "config": stage.config,
            })

        # Action nodes
        for action in workflow.actionnode_nodes.all():
            nodes.append({
                "node_type": "action",
                "node_id": action.node_id,
                "name": action.name,
                "action_type": action.action_type,
                "execution_mode": action.execution_mode,
                "action_config": action.action_config,
                "position_x": action.position_x,
                "position_y": action.position_y,
                "config": action.config,
            })

        # Build connections list
        connections = [
            {
                "from_node": conn.from_node,
                "to_node": conn.to_node,
                "connection_type": conn.connection_type,
            }
            for conn in workflow.connections.all()
        ]

        return JsonResponse({
            "canvas_data": workflow.canvas_data,
            "nodes": nodes,
            "connections": connections,
            "version": workflow.version,
            "name": workflow.name,
        })


class WorkflowDuplicateView(LoginRequiredMixin, WorkflowAccessMixin, View):
    """Duplicate a workflow template to the same or different organization."""

    def get(self, request, pk):
        from apps.organizations.services import PermissionService

        source_workflow = get_object_or_404(WorkflowTemplate, pk=pk)

        # Check if user can view the source workflow
        if not PermissionService.can_view_workflow(request.user, source_workflow):
            messages.error(request, "You don't have permission to view this workflow.")
            return redirect("packages:workflow_list")

        # Check if user can create workflows
        if not PermissionService.can_create_workflow(request.user):
            messages.error(request, "You don't have permission to create workflow templates.")
            return redirect("packages:workflow_list")

        user_orgs = self.get_user_organizations()
        organizations = Organization.objects.filter(id__in=user_orgs)

        return render(request, "packages/workflow_duplicate.html", {
            "source_workflow": source_workflow,
            "organizations": organizations,
        })

    def post(self, request, pk):
        from apps.organizations.services import PermissionService

        source_workflow = get_object_or_404(WorkflowTemplate, pk=pk)

        # Check permissions
        if not PermissionService.can_duplicate_workflow(request.user, source_workflow):
            messages.error(request, "You don't have permission to duplicate this workflow.")
            return redirect("packages:workflow_list")

        # Get target organization
        target_org_id = request.POST.get("organization")
        target_org = None
        if target_org_id:
            target_org = get_object_or_404(Organization, pk=target_org_id)
            # Verify user has access to target org
            if not PermissionService.can_create_workflow(request.user, target_org):
                messages.error(request, "You don't have permission to create workflows for this organization.")
                return redirect("packages:workflow_list")

        # Get new name
        new_name = request.POST.get("name", "").strip()
        if not new_name:
            new_name = f"{source_workflow.name} (Copy)"

        # Create the duplicate
        new_workflow = WorkflowTemplate.objects.create(
            organization=target_org,
            name=new_name,
            description=source_workflow.description,
            canvas_data=source_workflow.canvas_data,
            is_active=True,
            created_by=request.user,
        )

        # Duplicate stage nodes
        for stage in source_workflow.stagenode_nodes.all():
            new_stage = StageNode.objects.create(
                template=new_workflow,
                node_id=stage.node_id,
                name=stage.name,
                action_type=stage.action_type,
                multi_office_rule=stage.multi_office_rule,
                is_optional=stage.is_optional,
                timeout_days=stage.timeout_days,
                position_x=stage.position_x,
                position_y=stage.position_y,
                config=stage.config,
            )
            # Copy assigned offices
            new_stage.assigned_offices.set(stage.assigned_offices.all())

        # Duplicate action nodes
        for action in source_workflow.actionnode_nodes.all():
            ActionNode.objects.create(
                template=new_workflow,
                node_id=action.node_id,
                name=action.name,
                action_type=action.action_type,
                execution_mode=action.execution_mode,
                action_config=action.action_config,
                position_x=action.position_x,
                position_y=action.position_y,
                config=action.config,
            )

        # Duplicate connections
        for conn in source_workflow.connections.all():
            NodeConnection.objects.create(
                template=new_workflow,
                from_node=conn.from_node,
                to_node=conn.to_node,
                connection_type=conn.connection_type,
            )

        messages.success(request, f"Workflow '{new_workflow.name}' created as a copy.")
        return redirect("packages:workflow_builder", pk=new_workflow.pk)


# ============================================================================
# Routing Views
# ============================================================================


class PackageSubmitView(LoginRequiredMixin, View):
    """Submit a draft package into routing."""

    def post(self, request, pk):
        package = get_object_or_404(Package, pk=pk)

        # Check permission - must be originator
        if package.originator != request.user:
            messages.error(request, "You can only submit packages you created.")
            return redirect("packages:package_detail", pk=pk)

        try:
            service = RoutingService(package)
            service.submit_package(request.user)
            messages.success(
                request,
                f"Package {package.reference_number} submitted to routing."
            )
        except RoutingError as e:
            messages.error(request, str(e))

        return redirect("packages:package_detail", pk=pk)


class PackageConfigureRoutingView(LoginRequiredMixin, View):
    """Configure stage office assignments and action recipients before submitting."""

    def get(self, request, pk):
        package = get_object_or_404(Package, pk=pk)

        # Check permissions
        if package.originator != request.user and not request.user.is_superuser:
            messages.error(request, "You can only configure routing for packages you created.")
            return redirect("packages:package_detail", pk=pk)

        if package.status != Package.Status.DRAFT:
            messages.error(request, "Only draft packages can be configured for routing.")
            return redirect("packages:package_detail", pk=pk)

        if not package.workflow_template:
            messages.error(request, "Package must have a workflow template to configure routing.")
            return redirect("packages:package_detail", pk=pk)

        # Get stages and actions from workflow template
        stages = package.workflow_template.stagenode_nodes.all().prefetch_related(
            "assigned_offices"
        ).order_by("position_y", "position_x")
        actions = package.workflow_template.actionnode_nodes.filter(
            action_type__in=[ActionNode.ActionType.SEND_ALERT, ActionNode.ActionType.SEND_EMAIL]
        ).order_by("position_y", "position_x")

        # Build stage forms with existing assignments or template defaults
        stage_forms = []
        for stage in stages:
            # Check for existing package-specific assignment
            try:
                assignment = PackageStageAssignment.objects.get(
                    package=package, stage=stage
                )
                initial_offices = list(assignment.offices.values_list("id", flat=True))
            except PackageStageAssignment.DoesNotExist:
                # Use template defaults
                initial_offices = list(stage.assigned_offices.values_list("id", flat=True))

            form = PackageStageAssignmentForm(
                prefix=f"stage_{stage.node_id}",
                organization=package.organization,
                initial={
                    "stage_node_id": stage.node_id,
                    "stage_name": stage.name,
                    "offices": initial_offices,
                }
            )
            stage_forms.append({
                "stage": stage,
                "form": form,
            })

        # Build action recipient forms
        action_forms = []
        for action in actions:
            # Check for existing package-specific recipients
            existing = PackageActionRecipient.objects.filter(
                package=package, action_node=action
            ).first()

            initial = {
                "action_node_id": action.node_id,
                "action_name": action.name,
            }
            if existing:
                initial["recipient_type"] = existing.recipient_type
                if existing.user:
                    initial["user"] = existing.user.id
                    initial["user_display"] = existing.user.get_full_name() or existing.user.email
                if existing.office:
                    initial["office"] = existing.office.id
                if existing.email_address:
                    initial["email_address"] = existing.email_address

            form = PackageActionRecipientForm(
                prefix=f"action_{action.node_id}",
                organization=package.organization,
                initial=initial,
            )
            action_forms.append({
                "action": action,
                "form": form,
            })

        return render(request, "packages/configure_routing.html", {
            "package": package,
            "stage_forms": stage_forms,
            "action_forms": action_forms,
        })

    def post(self, request, pk):
        from django.db import transaction

        package = get_object_or_404(Package, pk=pk)

        # Check permissions
        if package.originator != request.user and not request.user.is_superuser:
            messages.error(request, "You can only configure routing for packages you created.")
            return redirect("packages:package_detail", pk=pk)

        if package.status != Package.Status.DRAFT:
            messages.error(request, "Only draft packages can be configured for routing.")
            return redirect("packages:package_detail", pk=pk)

        if not package.workflow_template:
            messages.error(request, "Package must have a workflow template to configure routing.")
            return redirect("packages:package_detail", pk=pk)

        # Get stages and actions from workflow template
        stages = package.workflow_template.stagenode_nodes.all().order_by("position_y", "position_x")
        actions = package.workflow_template.actionnode_nodes.filter(
            action_type__in=[ActionNode.ActionType.SEND_ALERT, ActionNode.ActionType.SEND_EMAIL]
        ).order_by("position_y", "position_x")

        # Validate and collect form data
        all_valid = True
        stage_forms = []
        action_forms = []

        for stage in stages:
            form = PackageStageAssignmentForm(
                request.POST,
                prefix=f"stage_{stage.node_id}",
                organization=package.organization,
            )
            if not form.is_valid():
                all_valid = False
            stage_forms.append({
                "stage": stage,
                "form": form,
            })

        for action in actions:
            form = PackageActionRecipientForm(
                request.POST,
                prefix=f"action_{action.node_id}",
                organization=package.organization,
            )
            if not form.is_valid():
                all_valid = False
            action_forms.append({
                "action": action,
                "form": form,
            })

        if not all_valid:
            return render(request, "packages/configure_routing.html", {
                "package": package,
                "stage_forms": stage_forms,
                "action_forms": action_forms,
            })

        # Save all assignments in a transaction
        with transaction.atomic():
            # Save stage assignments
            for item in stage_forms:
                stage = item["stage"]
                form = item["form"]
                offices = form.cleaned_data.get("offices", [])

                # Validate offices belong to package's organization
                if offices and package.organization:
                    invalid_offices = [o for o in offices if o.organization_id != package.organization_id]
                    if invalid_offices:
                        messages.error(request, "Selected offices must belong to the package's organization.")
                        return render(request, "packages/configure_routing.html", {
                            "package": package,
                            "stage_forms": stage_forms,
                            "action_forms": action_forms,
                        })

                # Delete existing assignment if any
                PackageStageAssignment.objects.filter(
                    package=package, stage=stage
                ).delete()

                # Create new assignment if offices were selected
                if offices:
                    assignment = PackageStageAssignment.objects.create(
                        package=package,
                        stage=stage,
                    )
                    assignment.offices.set(offices)

            # Save action recipients
            for item in action_forms:
                action = item["action"]
                form = item["form"]
                recipient_type = form.cleaned_data.get("recipient_type")

                # Delete existing recipients for this action
                PackageActionRecipient.objects.filter(
                    package=package, action_node=action
                ).delete()

                # Create new recipient if configured
                if recipient_type:
                    from django.contrib.auth import get_user_model
                    User = get_user_model()

                    recipient = PackageActionRecipient(
                        package=package,
                        action_node=action,
                        recipient_type=recipient_type,
                    )
                    if recipient_type == "user":
                        user_id = form.cleaned_data.get("user")
                        if user_id:
                            try:
                                recipient.user = User.objects.get(pk=user_id)
                            except User.DoesNotExist:
                                # Skip saving this recipient if user doesn't exist
                                continue
                    elif recipient_type == "office":
                        recipient.office = form.cleaned_data.get("office")
                    elif recipient_type == "email":
                        recipient.email_address = form.cleaned_data.get("email_address", "")
                    recipient.save()

        # Check if user wants to submit
        if "submit_to_routing" in request.POST:
            try:
                service = RoutingService(package)
                service.submit_package(request.user)
                messages.success(
                    request,
                    f"Package {package.reference_number} configured and submitted to routing."
                )
            except RoutingError as e:
                messages.error(request, str(e))
                return redirect("packages:package_detail", pk=pk)
        else:
            messages.success(request, "Routing configuration saved.")

        return redirect("packages:package_detail", pk=pk)


class StageActionView(LoginRequiredMixin, View):
    """Take action at the current workflow stage."""

    def get_user_office(self, user, package):
        """Get user's office that can act at current stage."""
        service = RoutingService(package)
        stage = service.get_current_stage()
        if not stage:
            return None

        # Get user's approved office memberships
        user_offices = OfficeMembership.objects.filter(
            user=user,
            status=OfficeMembership.STATUS_APPROVED,
        ).values_list("office_id", flat=True)

        # Find which of user's offices is assigned to this stage
        # Use package-specific assignment if available, else template default
        assigned_offices = service.get_offices_for_stage(stage)
        assigned = assigned_offices.filter(pk__in=user_offices).first()
        return assigned

    def get(self, request, pk):
        package = get_object_or_404(Package, pk=pk)

        if package.status != Package.Status.IN_ROUTING:
            messages.error(request, "Package is not currently in routing.")
            return redirect("packages:package_detail", pk=pk)

        office = self.get_user_office(request.user, package)
        if not office:
            messages.error(request, "You are not authorized to act on this package.")
            return redirect("packages:package_detail", pk=pk)

        service = RoutingService(package)
        return_choices = service.get_available_return_nodes()

        form = StageActionForm(return_node_choices=return_choices)
        stage = service.get_current_stage()

        return render(request, "packages/stage_action.html", {
            "package": package,
            "form": form,
            "stage": stage,
            "office": office,
        })

    def post(self, request, pk):
        package = get_object_or_404(Package, pk=pk)

        if package.status != Package.Status.IN_ROUTING:
            messages.error(request, "Package is not currently in routing.")
            return redirect("packages:package_detail", pk=pk)

        office = self.get_user_office(request.user, package)
        if not office:
            messages.error(request, "You are not authorized to act on this package.")
            return redirect("packages:package_detail", pk=pk)

        service = RoutingService(package)
        return_choices = service.get_available_return_nodes()
        form = StageActionForm(request.POST, return_node_choices=return_choices)

        if form.is_valid():
            try:
                # Get client IP
                x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
                if x_forwarded_for:
                    ip = x_forwarded_for.split(",")[0]
                else:
                    ip = request.META.get("REMOTE_ADDR")

                service.take_action(
                    user=request.user,
                    office=office,
                    action_type=form.cleaned_data["action_type"],
                    comment=form.cleaned_data.get("comment", ""),
                    return_to_node=form.cleaned_data.get("return_to_node", ""),
                    position=form.cleaned_data.get("position", ""),
                    ip_address=ip,
                )

                action_display = dict(StageActionForm.ACTION_CHOICES).get(
                    form.cleaned_data["action_type"], "Action"
                )
                messages.success(
                    request,
                    f"{action_display} recorded for {package.reference_number}."
                )
                return redirect("packages:package_detail", pk=pk)

            except RoutingError as e:
                messages.error(request, str(e))

        stage = service.get_current_stage()
        return render(request, "packages/stage_action.html", {
            "package": package,
            "form": form,
            "stage": stage,
            "office": office,
        })


class PackageManagementMixin:
    """Mixin to check if user can manage a package (pause/cancel/change priority)."""

    def can_manage_package(self, user, package):
        """Check if user can manage this package.

        Allowed: originator, org managers, originating office managers, superusers.
        """
        if user.is_superuser:
            return True

        if package.originator == user:
            return True

        # Check if user is an org manager for this package's org
        if OrganizationMembership.objects.filter(
            user=user,
            organization=package.organization,
            role=OrganizationMembership.ROLE_MANAGER,
            status=OrganizationMembership.STATUS_APPROVED,
        ).exists():
            return True

        # Check if user is manager of originating office
        if OfficeMembership.objects.filter(
            user=user,
            office=package.originating_office,
            role=OfficeMembership.ROLE_MANAGER,
            status=OfficeMembership.STATUS_APPROVED,
        ).exists():
            return True

        return False


class PackagePauseView(LoginRequiredMixin, AuditLogMixin, PackageManagementMixin, View):
    """Pause a package routing (put on hold)."""

    def post(self, request, pk):
        package = get_object_or_404(Package, pk=pk)

        if not self.can_manage_package(request.user, package):
            messages.error(request, "You don't have permission to manage this package.")
            return redirect("packages:package_detail", pk=pk)

        if package.status != Package.Status.IN_ROUTING:
            messages.error(request, "Only packages in routing can be paused.")
            return redirect("packages:package_detail", pk=pk)

        package.status = Package.Status.ON_HOLD
        package.save(update_fields=["status"])
        self.log_action(
            action="package_paused",
            resource_type="Package",
            resource_id=str(package.id),
            organization=package.organization,
        )
        messages.success(request, f"Package {package.reference_number} has been paused.")
        return redirect("packages:package_detail", pk=pk)


class PackageResumeView(LoginRequiredMixin, AuditLogMixin, PackageManagementMixin, View):
    """Resume a paused package routing."""

    def post(self, request, pk):
        package = get_object_or_404(Package, pk=pk)

        if not self.can_manage_package(request.user, package):
            messages.error(request, "You don't have permission to manage this package.")
            return redirect("packages:package_detail", pk=pk)

        if package.status != Package.Status.ON_HOLD:
            messages.error(request, "Only paused packages can be resumed.")
            return redirect("packages:package_detail", pk=pk)

        package.status = Package.Status.IN_ROUTING
        package.save(update_fields=["status"])
        self.log_action(
            action="package_resumed",
            resource_type="Package",
            resource_id=str(package.id),
            organization=package.organization,
        )
        messages.success(request, f"Package {package.reference_number} has been resumed.")
        return redirect("packages:package_detail", pk=pk)


class PackageCancelView(LoginRequiredMixin, AuditLogMixin, PackageManagementMixin, View):
    """Cancel a package routing."""

    def post(self, request, pk):
        package = get_object_or_404(Package, pk=pk)

        if not self.can_manage_package(request.user, package):
            messages.error(request, "You don't have permission to manage this package.")
            return redirect("packages:package_detail", pk=pk)

        if package.status not in [Package.Status.IN_ROUTING, Package.Status.ON_HOLD, Package.Status.DRAFT]:
            messages.error(request, "This package cannot be cancelled.")
            return redirect("packages:package_detail", pk=pk)

        package.status = Package.Status.CANCELLED
        package.save(update_fields=["status"])
        self.log_action(
            action="package_cancelled",
            resource_type="Package",
            resource_id=str(package.id),
            organization=package.organization,
        )
        messages.success(request, f"Package {package.reference_number} has been cancelled.")
        return redirect("packages:package_detail", pk=pk)


class PackagePriorityView(LoginRequiredMixin, AuditLogMixin, PackageManagementMixin, View):
    """Update package priority."""

    def post(self, request, pk):
        package = get_object_or_404(Package, pk=pk)

        if not self.can_manage_package(request.user, package):
            messages.error(request, "You don't have permission to manage this package.")
            return redirect("packages:package_detail", pk=pk)

        # Don't allow changing priority on completed/cancelled packages
        if package.status in [Package.Status.COMPLETED, Package.Status.CANCELLED]:
            messages.error(request, "Cannot change priority of completed or cancelled packages.")
            return redirect("packages:package_detail", pk=pk)

        new_priority = request.POST.get("priority")
        if new_priority not in [choice[0] for choice in Package.Priority.choices]:
            messages.error(request, "Invalid priority value.")
            return redirect("packages:package_detail", pk=pk)

        old_priority = package.priority
        package.priority = new_priority
        package.save(update_fields=["priority"])
        self.log_action(
            action="package_priority_changed",
            resource_type="Package",
            resource_id=str(package.id),
            organization=package.organization,
            details={"old_priority": old_priority, "new_priority": new_priority},
        )
        messages.success(request, f"Package priority updated to {package.get_priority_display()}.")
        return redirect("packages:package_detail", pk=pk)
