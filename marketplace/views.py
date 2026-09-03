"""Placeholder views for the marketplace app."""

from django.contrib.auth.decorators import login_required
from django.shortcuts import render


@login_required
def index(request):
    """Placeholder landing page until the marketplace agent ships the real UI."""
    return render(request, "marketplace/coming_soon.html", {"feature_title": "Marketplace"})
