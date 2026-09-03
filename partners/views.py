"""Placeholder views for the partners app."""

from django.contrib.auth.decorators import login_required
from django.shortcuts import render


@login_required
def index(request):
    """Placeholder landing page until the partners agent ships the real UI."""
    return render(request, "partners/coming_soon.html", {"feature_title": "Branding & Partners"})
