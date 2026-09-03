"""Placeholder views for the scheduling app."""

from django.contrib.auth.decorators import login_required
from django.shortcuts import render


@login_required
def index(request):
    """Placeholder landing page until the scheduling agent ships the real UI."""
    return render(request, "scheduling/coming_soon.html", {"feature_title": "Schedule"})
