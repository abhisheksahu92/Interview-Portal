"""Placeholder views for the offers app."""

from django.contrib.auth.decorators import login_required
from django.shortcuts import render


@login_required
def index(request):
    """Placeholder landing page until the offers agent ships the real UI."""
    return render(request, "offers/coming_soon.html", {"feature_title": "Offers"})
