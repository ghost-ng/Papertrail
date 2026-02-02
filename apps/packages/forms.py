"""Forms for package management."""

import json

from django import forms
from django.core.exceptions import ValidationError
from django.db.models import Max

from apps.core.models import SystemSetting
from apps.organizations.models import Office
from apps.packages.models import Package, Tab, Document, WorkflowTemplate, StageNode, ActionNode


class PackageForm(forms.ModelForm):
    """Form for creating and editing packages."""

    class Meta:
        model = Package
        fields = ["title", "priority", "workflow_template"]
        widgets = {
            "title": forms.TextInput(attrs={"class": "input", "placeholder": "Enter package title"}),
            "priority": forms.Select(attrs={"class": "input"}),
            "workflow_template": forms.Select(attrs={"class": "input"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["workflow_template"].required = False


class TabForm(forms.ModelForm):
    """Form for creating and editing tabs."""

    class Meta:
        model = Tab
        fields = ["display_name", "is_required"]
        widgets = {
            "display_name": forms.TextInput(attrs={"class": "input", "placeholder": "Enter tab name"}),
            "is_required": forms.CheckboxInput(attrs={"class": "form-checkbox"}),
        }

    def __init__(self, *args, package=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.package = package

    def save(self, commit=True):
        instance = super().save(commit=False)
        if not instance.pk:
            instance.identifier = Tab.get_next_identifier(self.package)
            max_order = self.package.tabs.aggregate(Max("order"))["order__max"]
            instance.order = (max_order or 0) + 1
            instance.package = self.package
        if commit:
            instance.save()
        return instance


class DocumentUploadForm(forms.Form):
    """Form for uploading documents."""

    file = forms.FileField(widget=forms.FileInput(attrs={"class": "input", "accept": ".pdf,.docx,.xlsx,.png,.jpg,.gif"}))

    def __init__(self, *args, tab=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.tab = tab
        self._max_size_mb = SystemSetting.get_value("max_file_size_mb", 50)

    def clean_file(self):
        file = self.cleaned_data.get("file")
        if not file:
            raise ValidationError("File is required.")

        max_size_bytes = self._max_size_mb * 1024 * 1024
        if file.size > max_size_bytes:
            raise ValidationError(f"File size ({file.size / 1024 / 1024:.1f}MB) exceeds maximum ({self._max_size_mb}MB).")

        allowed_types = SystemSetting.get_value("allowed_file_types", ["pdf", "docx", "xlsx", "png", "jpg", "gif"])
        ext = file.name.split(".")[-1].lower() if "." in file.name else ""
        if ext not in allowed_types:
            raise ValidationError(f"File type '.{ext}' not allowed. Allowed: {', '.join(allowed_types)}")

        return file

    def save(self, uploaded_by):
        file = self.cleaned_data["file"]
        document = Document(
            tab=self.tab,
            version=Document.get_next_version(self.tab),
            file=file,
            filename=file.name,
            file_size=file.size,
            mime_type=file.content_type or "application/octet-stream",
            uploaded_by=uploaded_by,
            is_current=True,
        )
        document.save()
        return document


class WorkflowTemplateForm(forms.ModelForm):
    """Form for creating and editing workflow templates."""

    class Meta:
        model = WorkflowTemplate
        fields = ["name", "description", "organization", "is_active"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "input", "placeholder": "Enter workflow name"}),
            "description": forms.Textarea(attrs={"class": "input", "rows": 3, "placeholder": "Describe the workflow purpose"}),
            "organization": forms.Select(attrs={"class": "input"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-checkbox"}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.fields["organization"].required = False
        self.fields["organization"].empty_label = "Shared (all organizations)"


class StageNodeForm(forms.ModelForm):
    """Form for configuring stage nodes."""

    class Meta:
        model = StageNode
        fields = [
            "name", "action_type", "assigned_offices",
            "is_optional", "timeout_days", "escalation_office"
        ]
        widgets = {
            "name": forms.TextInput(attrs={"class": "input", "placeholder": "Stage name"}),
            "action_type": forms.Select(attrs={"class": "input"}),
            "assigned_offices": forms.SelectMultiple(attrs={"class": "input", "size": 5}),
            "is_optional": forms.CheckboxInput(attrs={"class": "form-checkbox"}),
            "timeout_days": forms.NumberInput(attrs={"class": "input", "min": 0}),
            "escalation_office": forms.Select(attrs={"class": "input"}),
        }

    def __init__(self, *args, organization=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.organization = organization

        # Filter offices by organization if provided
        if organization:
            org_offices = Office.objects.filter(organization=organization)
            self.fields["assigned_offices"].queryset = org_offices
            self.fields["escalation_office"].queryset = org_offices
        else:
            self.fields["assigned_offices"].queryset = Office.objects.all()
            self.fields["escalation_office"].queryset = Office.objects.all()

        self.fields["escalation_office"].required = False
        self.fields["timeout_days"].required = False


class ActionNodeForm(forms.ModelForm):
    """Form for configuring action nodes with JSON validation."""

    action_config_json = forms.CharField(
        widget=forms.Textarea(attrs={
            "class": "input font-mono text-sm",
            "rows": 6,
            "placeholder": '{\n  "key": "value"\n}'
        }),
        required=False,
        help_text="JSON configuration for the action"
    )

    class Meta:
        model = ActionNode
        fields = ["name", "action_type", "execution_mode"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "input", "placeholder": "Action name"}),
            "action_type": forms.Select(attrs={"class": "input"}),
            "execution_mode": forms.Select(attrs={"class": "input"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Pre-populate JSON field from instance
        if self.instance and self.instance.pk:
            self.fields["action_config_json"].initial = json.dumps(
                self.instance.action_config, indent=2
            ) if self.instance.action_config else "{}"

    def clean_action_config_json(self):
        """Validate that action_config_json is valid JSON."""
        json_str = self.cleaned_data.get("action_config_json", "").strip()
        if not json_str:
            return {}
        try:
            return json.loads(json_str)
        except json.JSONDecodeError as e:
            raise ValidationError(f"Invalid JSON: {e}")

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.action_config = self.cleaned_data.get("action_config_json", {})
        if commit:
            instance.save()
        return instance


class StageActionForm(forms.Form):
    """Form for taking action at a workflow stage."""

    ACTION_CHOICES = [
        ("complete", "Complete"),
        ("return", "Return for Revision"),
        ("reject", "Reject"),
    ]

    action_type = forms.ChoiceField(
        choices=ACTION_CHOICES,
        widget=forms.RadioSelect(attrs={"class": "form-radio"}),
        initial="complete",
    )
    comment = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            "class": "input",
            "rows": 3,
            "placeholder": "Add a comment (required for return/reject)",
        }),
    )
    return_to_node = forms.ChoiceField(
        required=False,
        widget=forms.Select(attrs={"class": "input"}),
    )
    position = forms.CharField(
        required=False,
        max_length=200,
        widget=forms.TextInput(attrs={
            "class": "input",
            "placeholder": "Your position/title (optional)",
        }),
    )

    def __init__(self, *args, return_node_choices=None, **kwargs):
        super().__init__(*args, **kwargs)
        if return_node_choices:
            self.fields["return_to_node"].choices = [("", "Select destination...")] + list(return_node_choices)
        else:
            self.fields["return_to_node"].choices = [("", "No return destinations available")]

    def clean(self):
        cleaned_data = super().clean()
        action_type = cleaned_data.get("action_type")
        comment = cleaned_data.get("comment", "").strip()
        return_to_node = cleaned_data.get("return_to_node")

        if action_type in ("return", "reject") and not comment:
            raise forms.ValidationError(
                f"A comment is required when {action_type}ing a package."
            )

        if action_type == "return" and not return_to_node:
            raise forms.ValidationError(
                "Please select a destination for the return."
            )

        return cleaned_data