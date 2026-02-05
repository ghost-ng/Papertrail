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

from apps.organizations.models import OrganizationMembership, OfficeMembership, Organization, Office
from apps.packages.forms import PackageForm, TabForm, DocumentUploadForm, WorkflowTemplateForm, StageActionForm
from apps.packages.models import Package, Tab, Document, WorkflowTemplate, StageNode, ActionNode, NodeConnection
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

        # Add routing context if in routing
        if package.status == Package.Status.IN_ROUTING and package.workflow_template:
            service = RoutingService(package)
            context["current_stage"] = service.get_current_stage()

            # Check if user can act
            stage = context["current_stage"]
            if stage:
                user_offices = OfficeMembership.objects.filter(
                    user=self.request.user,
                    status=OfficeMembership.STATUS_APPROVED,
                ).values_list("office_id", flat=True)
                context["can_act"] = stage.assigned_offices.filter(pk__in=user_offices).exists()
            else:
                context["can_act"] = False

        return context


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
    def get(self, request, tab_pk):
        tab = get_object_or_404(Tab, pk=tab_pk)
        form = DocumentUploadForm(tab=tab)
        return render(request, "packages/document_upload.html", {"tab": tab, "package": tab.package, "form": form})

    def post(self, request, tab_pk):
        tab = get_object_or_404(Tab, pk=tab_pk)
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
        assigned = stage.assigned_offices.filter(pk__in=user_offices).first()
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
