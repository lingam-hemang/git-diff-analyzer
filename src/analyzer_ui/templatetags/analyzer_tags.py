"""Custom template filters for the analyzer UI."""

from django import template

register = template.Library()


@register.filter
def priority_class(priority: str) -> str:
    """Map priority string to a Bootstrap badge class."""
    mapping = {
        "high": "danger",
        "medium": "warning",
        "low": "secondary",
    }
    return mapping.get(str(priority).lower(), "secondary")


@register.filter
def truncate_hash(value: str, length: int = 12) -> str:
    """Return the first `length` characters of a commit hash."""
    return str(value)[:length]
