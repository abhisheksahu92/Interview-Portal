"""Placeholder views for the analytics app."""

from django.contrib.auth.decorators import login_required
from django.shortcuts import render


@login_required
def index(request):
    """Placeholder landing page until the analytics agent ships the real UI."""
    return render(request, "analytics/coming_soon.html", {"feature_title": "Analytics"})
