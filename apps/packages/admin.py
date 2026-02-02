"""Admin configuration for packages app."""

from django.contrib import admin
from django.utils.html import format_html

from apps.packages.models import (
    Package, Tab, Document, WorkflowTemplate,
    StageNode, ActionNode, NodeConnection
)


class TabInline(admin.TabularInline):
    model = Tab
    extra = 0
    readonly_fields = ["identifier", "created_at"]
    fields = ["identifier", "display_name", "order", "is_required", "created_at"]


class DocumentInline(admin.TabularInline):
    model = Document
    extra = 0
    readonly_fields = ["version", "sha256_hash", "uploaded_by", "uploaded_at", "file_size"]
    fields = ["version", "filename", "file", "mime_type", "file_size", "is_current", "uploaded_by", "uploaded_at"]


@admin.register(Package)
class PackageAdmin(admin.ModelAdmin):
    list_display = ["reference_number", "title", "organization", "status_badge", "priority_badge", "originator", "created_at"]
    list_filter = ["status", "priority", "organization", "created_at"]
    search_fields = ["reference_number", "title", "originator__email"]
    readonly_fields = ["reference_number", "created_at", "updated_at", "submitted_at", "completed_at"]
    inlines = [TabInline]
    date_hierarchy = "created_at"

    fieldsets = [
        (None, {"fields": ["reference_number", "title", "organization", "originator", "originating_office"]}),
        ("Status", {"fields": ["status", "priority", "priority_deadline", "current_node", "integrity_violation"]}),
        ("Workflow", {"fields": ["workflow_template"]}),
        ("Timestamps", {"fields": ["created_at", "updated_at", "submitted_at", "completed_at"], "classes": ["collapse"]}),
        ("Archive", {"fields": ["archived_at", "archived_by", "archive_reason"], "classes": ["collapse"]}),
    ]

    def status_badge(self, obj):
        colors = {"draft": "gray", "in_routing": "blue", "completed": "green", "cancelled": "red", "on_hold": "yellow", "archived": "gray"}
        return format_html('<span style="background-color: {}; color: white; padding: 2px 8px; border-radius: 4px;">{}</span>', colors.get(obj.status, "gray"), obj.get_status_display())
    status_badge.short_description = "Status"

    def priority_badge(self, obj):
        colors = {"low": "#9CA3AF", "normal": "#3B82F6", "urgent": "#EF4444"}
        return format_html('<span style="color: {}; font-weight: bold;">{}</span>', colors.get(obj.priority, "#9CA3AF"), obj.get_priority_display())
    priority_badge.short_description = "Priority"


@admin.register(Tab)
class TabAdmin(admin.ModelAdmin):
    list_display = ["identifier", "display_name", "package", "order", "is_required", "document_count"]
    list_filter = ["is_required", "package__organization"]
    search_fields = ["identifier", "display_name", "package__reference_number"]
    readonly_fields = ["identifier", "created_at"]
    inlines = [DocumentInline]

    def document_count(self, obj):
        return obj.documents.count()
    document_count.short_description = "Documents"


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ["filename", "tab", "version", "is_current", "file_size_display", "uploaded_by", "uploaded_at"]
    list_filter = ["is_current", "mime_type", "uploaded_at"]
    search_fields = ["filename", "tab__package__reference_number", "sha256_hash"]
    readonly_fields = ["sha256_hash", "uploaded_at"]

    def file_size_display(self, obj):
        size = obj.file_size
        for unit in ["B", "KB", "MB", "GB"]:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"
    file_size_display.short_description = "Size"


class StageNodeInline(admin.TabularInline):
    model = StageNode
    extra = 0
    readonly_fields = ["node_id", "created_at"]
    fields = ["node_id", "name", "action_type", "is_optional", "timeout_days", "position_x", "position_y", "created_at"]


class ActionNodeInline(admin.TabularInline):
    model = ActionNode
    extra = 0
    readonly_fields = ["node_id", "created_at"]
    fields = ["node_id", "name", "action_type", "execution_mode", "position_x", "position_y", "created_at"]


class NodeConnectionInline(admin.TabularInline):
    model = NodeConnection
    extra = 0
    readonly_fields = ["created_at"]
    fields = ["from_node", "to_node", "connection_type", "created_at"]


@admin.register(WorkflowTemplate)
class WorkflowTemplateAdmin(admin.ModelAdmin):
    list_display = ["name", "organization", "is_active", "node_count", "version", "created_at"]
    list_filter = ["is_active", "organization"]
    search_fields = ["name", "description"]
    readonly_fields = ["version", "created_at", "updated_at"]
    inlines = [StageNodeInline, ActionNodeInline, NodeConnectionInline]

    fieldsets = [
        (None, {"fields": ["name", "description", "organization", "created_by"]}),
        ("Status", {"fields": ["is_active", "version"]}),
        ("Canvas Data", {"fields": ["canvas_data"], "classes": ["collapse"]}),
        ("Timestamps", {"fields": ["created_at", "updated_at"], "classes": ["collapse"]}),
    ]

    def node_count(self, obj):
        stage_count = obj.stagenode_nodes.count()
        action_count = obj.actionnode_nodes.count()
        return f"{stage_count} stages, {action_count} actions"
    node_count.short_description = "Nodes"


@admin.register(StageNode)
class StageNodeAdmin(admin.ModelAdmin):
    list_display = ["name", "template", "action_type", "is_optional", "timeout_days"]
    list_filter = ["action_type", "is_optional", "template__organization"]
    search_fields = ["name", "node_id", "template__name"]
    readonly_fields = ["node_id", "node_type", "created_at", "updated_at"]
    filter_horizontal = ["assigned_offices"]

    fieldsets = [
        (None, {"fields": ["template", "node_id", "name", "node_type"]}),
        ("Stage Configuration", {"fields": ["action_type", "assigned_offices"]}),
        ("Optional Settings", {"fields": ["is_optional", "timeout_days", "escalation_office"]}),
        ("Position", {"fields": ["position_x", "position_y"]}),
        ("Config", {"fields": ["config"], "classes": ["collapse"]}),
        ("Timestamps", {"fields": ["created_at", "updated_at"], "classes": ["collapse"]}),
    ]


@admin.register(ActionNode)
class ActionNodeAdmin(admin.ModelAdmin):
    list_display = ["name", "template", "action_type", "execution_mode"]
    list_filter = ["action_type", "execution_mode", "template__organization"]
    search_fields = ["name", "node_id", "template__name"]
    readonly_fields = ["node_id", "node_type", "created_at", "updated_at"]

    fieldsets = [
        (None, {"fields": ["template", "node_id", "name", "node_type"]}),
        ("Action Configuration", {"fields": ["action_type", "execution_mode", "action_config"]}),
        ("Position", {"fields": ["position_x", "position_y"]}),
        ("Config", {"fields": ["config"], "classes": ["collapse"]}),
        ("Timestamps", {"fields": ["created_at", "updated_at"], "classes": ["collapse"]}),
    ]


@admin.register(NodeConnection)
class NodeConnectionAdmin(admin.ModelAdmin):
    list_display = ["__str__", "template", "from_node", "to_node", "connection_type"]
    list_filter = ["connection_type", "template__organization"]
    search_fields = ["from_node", "to_node", "template__name"]
    readonly_fields = ["created_at", "updated_at"]

    fieldsets = [
        (None, {"fields": ["template", "from_node", "to_node", "connection_type"]}),
        ("Timestamps", {"fields": ["created_at", "updated_at"], "classes": ["collapse"]}),
    ]
