"""Logout is POST-only and the active company survives a re-login."""

import pytest
from django.urls import reverse

from core.middleware import SESSION_COMPANY_KEY
from core.models import Company, Membership, User


@pytest.fixture
def user_with_two_companies(db):
    user = User.objects.create_user(email="multi@example.com", password="pw12345!")
    first = Company.objects.create(name="Alpha Staffing")
    second = Company.objects.create(name="Zeta Staffing")
    Membership.objects.create(user=user, company=first, role=Membership.OWNER)
    Membership.objects.create(user=user, company=second, role=Membership.RECRUITER)
    return user, first, second


def test_logout_get_shows_a_confirm_page(client, db):
    user = User.objects.create_user(email="a@example.com", password="pw12345!")
    client.force_login(user)
    resp = client.get(reverse("core:logout"))
    assert resp.status_code == 200
    assert "Sign out" in resp.content.decode()
    # Still signed in: GET must not mutate.
    assert client.session.get("_auth_user_id") == str(user.pk)


def test_logout_get_when_anonymous_redirects(client, db):
    resp = client.get(reverse("core:logout"))
    assert resp.status_code == 302
    assert resp["Location"] == reverse("core:login")


def test_logout_post_signs_out(client, db):
    user = User.objects.create_user(email="b@example.com", password="pw12345!")
    client.force_login(user)
    resp = client.post(reverse("core:logout"))
    assert resp.status_code == 302
    assert "_auth_user_id" not in client.session


def test_switch_company_persists_last_company(client, user_with_two_companies):
    user, _first, second = user_with_two_companies
    client.force_login(user)
    client.post(reverse("core:switch_company"), {"company_id": second.pk})
    user.refresh_from_db()
    assert user.last_company_id == second.pk


def test_relogin_restores_last_used_company(client, user_with_two_companies):
    user, first, second = user_with_two_companies
    client.force_login(user)
    client.post(reverse("core:switch_company"), {"company_id": second.pk})
    client.post(reverse("core:logout"))

    client.post(
        reverse("core:login"), {"username": user.email, "password": "pw12345!"}
    )
    resp = client.get(reverse("core:account_home"))
    assert resp.wsgi_request.company == second
    assert client.session[SESSION_COMPANY_KEY] == second.pk
    assert first != second


def test_first_membership_is_remembered(client, user_with_two_companies):
    user, first, _second = user_with_two_companies
    client.force_login(user)
    client.get(reverse("core:account_home"))
    user.refresh_from_db()
    assert user.last_company_id == first.pk
