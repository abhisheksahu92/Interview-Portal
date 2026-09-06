"""The four public policy pages Razorpay's merchant review needs to find."""

import pytest
from django.urls import reverse

from web.legal import POLICY_UPDATED, POLICY_VERSION

PAGES = [
    ("web:terms", "/legal/terms/", "Terms of Service"),
    ("web:privacy", "/legal/privacy/", "Privacy Policy"),
    ("web:refunds", "/legal/refunds/", "Refund &amp; Cancellation Policy"),
    ("web:contact", "/contact/", "Contact us"),
]


@pytest.mark.parametrize("name,path,heading", PAGES)
def test_policy_page_renders_for_anonymous(client, name, path, heading):
    assert reverse(name) == path
    response = client.get(path)
    assert response.status_code == 200
    body = response.content.decode()
    assert f"<h1 class=\"mb-1\">{heading}</h1>" in body


@pytest.mark.parametrize("name,path,heading", PAGES)
def test_policy_page_stamps_one_shared_version(client, name, path, heading):
    body = client.get(path).content.decode()
    assert POLICY_VERSION in body
    assert POLICY_UPDATED.strftime("%Y") in body
    assert "Last updated" in body


@pytest.mark.parametrize("name,path,heading", PAGES)
def test_policy_page_carries_the_not_legal_advice_banner(client, name, path, heading):
    body = client.get(path).content.decode()
    assert "This is a template, not legal advice." in body
    assert 'data-bs-dismiss="alert"' in body


@pytest.mark.parametrize("name,path,heading", PAGES)
def test_policy_page_has_its_own_title_and_description(client, name, path, heading):
    body = client.get(path).content.decode()
    # The base template's generic description must have been overridden.
    assert "Hiring pipelines, AI screening and placement billing" not in body
    assert "<title>" in body


def test_landing_footer_links_to_all_four_pages(client):
    body = client.get(reverse("web:home")).content.decode()
    for _name, path, _heading in PAGES:
        assert f'href="{path}"' in body


@pytest.mark.parametrize("path", ["/accounts/signup/", "/accounts/signup/company/"])
def test_signup_pages_link_to_the_policies(client, path):
    body = client.get(path).content.decode()
    assert 'href="/legal/terms/"' in body
    assert 'href="/legal/privacy/"' in body


@pytest.mark.parametrize("name,path,heading", PAGES)
def test_policy_pages_are_crawlable(client, name, path, heading):
    """robots.txt must not sit a Disallow prefix in front of a policy page."""
    lines = client.get("/robots.txt").content.decode().splitlines()
    disallowed = [
        ln.split(":", 1)[1].strip()
        for ln in lines
        if ln.lower().startswith("disallow:") and ln.split(":", 1)[1].strip()
    ]
    assert not any(path.startswith(prefix) for prefix in disallowed)
    assert b"noindex" not in client.get(path).content


def test_privacy_does_not_promise_a_self_service_export(client):
    """We have no export/delete flow yet; the page must not imply otherwise."""
    body = client.get("/legal/privacy/").content.decode()
    assert "no self-service export or delete button" in body


def test_contact_page_flags_the_blanks_the_owner_must_fill(client):
    body = client.get("/contact/").content.decode()
    assert "Not filled in yet." in body
    assert "REGISTERED_ADDRESS" in body
