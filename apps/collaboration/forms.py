"""Forms for collaboration app."""

from django import forms

from apps.collaboration.models import Comment


class CommentForm(forms.ModelForm):
    """Form for creating and editing comments."""

    class Meta:
        model = Comment
        fields = ["content", "visibility"]
        widgets = {
            "content": forms.Textarea(
                attrs={
                    "class": "input",
                    "rows": 3,
                    "placeholder": "Add a comment...",
                }
            ),
            "visibility": forms.Select(attrs={"class": "input"}),
        }
