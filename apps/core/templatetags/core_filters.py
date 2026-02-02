"""Custom template filters for core app."""

from django import template

register = template.Library()


@register.filter(name="replace")
def replace(value, args):
    """
    Replace occurrences in a string.

    Usage: {{ value|replace:"old:new" }}
    Example: {{ "hello_world"|replace:"_: " }} -> "hello world"
    """
    if not value:
        return value

    try:
        old, new = args.split(":")
        return str(value).replace(old, new)
    except ValueError:
        return value


@register.filter(name="pretty_key")
def pretty_key(value):
    """
    Convert a setting key to a pretty display name.

    Example: "brand_primary_color" -> "Primary Color"
    """
    if not value:
        return value

    # Remove common prefixes
    result = str(value)
    for prefix in ["brand_", "support_", "login_"]:
        if result.startswith(prefix):
            result = result[len(prefix):]
            break

    # Replace underscores with spaces and title case
    return result.replace("_", " ").title()
