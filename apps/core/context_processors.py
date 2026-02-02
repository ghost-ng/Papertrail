"""Context processors for core app."""

from apps.core.models import SystemSetting


def branding(request):
    """Add branding settings to template context."""
    return {
        "brand_name": SystemSetting.get_value("brand_name", "Papertrail"),
        "brand_logo_url": SystemSetting.get_value("brand_logo_url", None),
        "brand_primary_color": SystemSetting.get_value("brand_primary_color", "#2563eb"),
        "brand_accent_color": SystemSetting.get_value("brand_accent_color", "#1d4ed8"),
        "support_email": SystemSetting.get_value("support_email", None),
        "login_banner_text": SystemSetting.get_value("login_banner_text", None),
        "footer_text": SystemSetting.get_value("footer_text", None),
    }


def dark_mode(request):
    """Add dark mode preference to template context."""
    # Check user preference if authenticated, otherwise use cookie/default
    if request.user.is_authenticated:
        # Could store in user profile, for now use session
        dark = request.session.get("dark_mode", False)
    else:
        dark = request.COOKIES.get("dark_mode", "false") == "true"
    return {"dark_mode": dark}
