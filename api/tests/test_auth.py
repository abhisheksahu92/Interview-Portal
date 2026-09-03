"""Auth, schema and membership endpoints."""

import pytest
from rest_framework.authtoken.models import Token

from core.models import User


@pytest.mark.django_db
def test_token_obtain_returns_token_and_companies(api, owner_a, company_a):
    resp = api.post(
        "/api/v1/auth/token/",
        {"email": owner_a.email, "password": "pw12345!"},
        format="json",
    )
    assert resp.status_code == 200
    assert resp.data["token"] == Token.objects.get(user=owner_a).key
    assert [c["slug"] for c in resp.data["companies"]] == [company_a.slug]


@pytest.mark.django_db
def test_token_obtain_rejects_bad_password(api, owner_a):
    resp = api.post(
        "/api/v1/auth/token/",
        {"email": owner_a.email, "password": "nope"},
        format="json",
    )
    assert resp.status_code == 400


@pytest.mark.django_db
def test_anonymous_access_is_denied(api):
    resp = api.get("/api/v1/jobs/")
    # TokenAuthentication is first, so anonymous calls get a proper 401.
    assert resp.status_code == 401
    assert resp["WWW-Authenticate"].startswith("Token")


@pytest.mark.django_db
def test_token_auth_grants_access(auth, recruiter_a):
    assert auth(recruiter_a).get("/api/v1/jobs/").status_code == 200


@pytest.mark.django_db
def test_user_without_membership_sees_no_jobs(auth, db, job_a):
    loner = User.objects.create_user(email="loner@example.com", password="pw12345!")
    resp = auth(loner).get("/api/v1/jobs/")
    assert resp.status_code == 403


@pytest.mark.django_db
def test_memberships_endpoint_lists_only_own_company(
    auth, owner_a, recruiter_a, recruiter_b
):
    resp = auth(owner_a).get("/api/v1/memberships/")
    assert resp.status_code == 200
    emails = {m["user"]["email"] for m in resp.data["results"]}
    assert emails == {owner_a.email, recruiter_a.email}


@pytest.mark.django_db
def test_companies_endpoint_lists_only_own_companies(auth, owner_a, company_b):
    resp = auth(owner_a).get("/api/v1/companies/")
    slugs = [c["slug"] for c in resp.data["results"]]
    assert company_b.slug not in slugs


@pytest.mark.django_db
def test_schema_endpoint_is_served(auth, owner_a):
    resp = auth(owner_a).get("/api/schema/")
    assert resp.status_code == 200
