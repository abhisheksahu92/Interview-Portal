"""HTMX plumbing: CSRF header path and auth redirects."""

import re

import pytest
from django.test import Client
from django.urls import reverse

from core.models import Company, Membership, User


@pytest.fixture
def owner(db):
    user = User.objects.create_user(email="owner@example.com", password="pw12345!")
    company = Company.objects.create(name="Acme Staffing")
    Membership.objects.create(user=user, company=company, role=Membership.OWNER)
    return user, company


def test_base_template_sets_hx_headers(client, owner):
    user, _ = owner
    client.force_login(user)
    html = client.get(reverse("core:account_home")).content.decode()
    match = re.search(r"<body hx-headers='(\{[^']+\})'>", html)
    assert match, "body must carry hx-headers for bare hx-post buttons"
    assert "X-CSRFToken" in match.group(1)
    token = re.search(r'"X-CSRFToken": "([^"]+)"', match.group(1)).group(1)
    assert len(token) > 20


def test_hx_post_with_csrf_header_is_accepted(owner):
    """Real-browser equivalent: htmx sends the token as a header, not a field."""
    user, company = owner
    client = Client(enforce_csrf_checks=True)
    client.force_login(user)
    html = client.get(reverse("core:account_home")).content.decode()
    token = re.search(r'"X-CSRFToken": "([^"]+)"', html).group(1)

    # Without the header the POST is rejected...
    denied = client.post(
        reverse("core:switch_company"),
        {"company_id": company.pk},
        headers={"hx-request": "true"},
    )
    assert denied.status_code == 403

    # ...and with the header htmx puts on every request it succeeds.
    resp = client.post(
        reverse("core:switch_company"),
        {"company_id": company.pk},
        headers={"hx-request": "true", "x-csrftoken": token},
    )
    assert resp.status_code == 302


def test_expired_session_hx_request_gets_hx_redirect(client, db):
    resp = client.get(reverse("core:account_home"), headers={"hx-request": "true"})
    assert resp.status_code == 204
    assert resp["HX-Redirect"] == "/accounts/login/?next=/accounts/"
    assert resp.content == b""


def test_non_hx_request_still_gets_a_plain_redirect(client, db):
    resp = client.get(reverse("core:account_home"))
    assert resp.status_code == 302
    assert resp["Location"] == "/accounts/login/?next=/accounts/"


def test_hx_redirect_leaves_other_redirects_alone(client, owner):
    user, company = owner
    client.force_login(user)
    resp = client.post(
        reverse("core:switch_company"),
        {"company_id": company.pk},
        headers={"hx-request": "true"},
    )
    assert resp.status_code == 302
    assert "HX-Redirect" not in resp
