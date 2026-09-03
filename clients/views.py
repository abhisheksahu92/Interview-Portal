"""Placeholder views for the clients app."""

from django.contrib.auth.decorators import login_required
from django.shortcuts import render


@login_required
def index(request):
    """Placeholder landing page until the clients agent ships the real UI."""
    return render(request, "clients/coming_soon.html", {"feature_title": "Clients"})
