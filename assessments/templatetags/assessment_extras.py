"""Small template helpers for assessment screens."""

from django import template

register = template.Library()


@register.filter
def get_item(mapping, key):
    """Look up ``key`` in a dict-like answers payload (JSON keys are strings)."""
    if not hasattr(mapping, "get"):
        return None
    return mapping.get(str(key), mapping.get(key))
