"""Branded error pages."""

import pytest
from django.template.loader import render_to_string
from django.test import RequestFactory
from django.views.defaults import bad_request, permission_denied

from core.models import User


@pytest.mark.django_db
def test_404_page_renders_with_branding(client, settings):
    settings.DEBUG = False
    resp = client.get("/definitely-not-a-page/")
    assert resp.status_code == 404
    body = resp.content.decode()
    assert "404" in body
    assert "Interview Portal" in body
    assert "We could not find that page" in body


@pytest.mark.django_db
def test_403_page_renders_with_branding():
    request = RequestFactory().get("/anything/")
    request.user = User.objects.create_user(email="x@example.com", password="pw12345!")
    resp = permission_denied(request, Exception("nope"), template_name="403.html")
    assert resp.status_code == 403
    body = resp.content.decode()
    assert "403" in body
    assert "Interview Portal" in body
    assert "Access denied" in body


@pytest.mark.django_db
def test_400_page_renders():
    request = RequestFactory().get("/anything/")
    resp = bad_request(request, Exception("bad"), template_name="400.html")
    assert resp.status_code == 400
    assert "Bad request" in resp.content.decode()


def test_500_page_is_standalone():
    """The 500 page must render with no request and no context processors."""
    body = render_to_string("500.html")
    assert "Interview Portal" in body
    assert "500" in body
    # No inheritance from base.html: nothing that needs the DB or the tenant.
    assert "ip-shell" not in body
    assert "current_company" not in body
