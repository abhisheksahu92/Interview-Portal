"""Placeholder views for the careers app."""

from django.contrib.auth.decorators import login_required
from django.shortcuts import render


@login_required
def index(request):
    """Placeholder landing page until the careers agent ships the real UI."""
    return render(request, "careers/coming_soon.html", {"feature_title": "Careers"})
