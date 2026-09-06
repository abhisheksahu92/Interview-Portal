"""Signup consent: the checkbox is required and what it agreed to is recorded."""

import pytest
from django.urls import reverse

from core.models import Company, User
from web.legal import POLICY_VERSION

CANDIDATE = {
    "email": "consent-cand@x.com",
    "password1": "sup3r-secret-pw",
    "password2": "sup3r-secret-pw",
}
COMPANY = {
    "company_name": "Consent Staffing",
    "email": "consent-own@x.com",
    "password1": "sup3r-secret-pw",
    "password2": "sup3r-secret-pw",
}


@pytest.mark.django_db
def test_candidate_signup_without_consent_fails_and_creates_no_user(client):
    response = client.post(reverse("core:candidate_signup"), CANDIDATE)
    assert response.status_code == 200
    assert "accept_policies" in response.context["form"].errors
    assert "must accept" in str(response.context["form"].errors["accept_policies"])
    assert not User.objects.filter(email=CANDIDATE["email"]).exists()


@pytest.mark.django_db
def test_company_signup_without_consent_fails_and_creates_nothing(client):
    response = client.post(reverse("core:company_signup"), COMPANY)
    assert response.status_code == 200
    assert "accept_policies" in response.context["form"].errors
    assert not User.objects.filter(email=COMPANY["email"]).exists()
    assert not Company.objects.filter(name=COMPANY["company_name"]).exists()


@pytest.mark.django_db
def test_candidate_signup_with_consent_stamps_the_version(client):
    response = client.post(
        reverse("core:candidate_signup"), {**CANDIDATE, "accept_policies": "on"}
    )
    assert response.status_code == 302
    user = User.objects.get(email=CANDIDATE["email"])
    assert user.policy_version == POLICY_VERSION
    assert user.policy_accepted_at is not None


@pytest.mark.django_db
def test_company_signup_with_consent_stamps_the_version(client):
    response = client.post(
        reverse("core:company_signup"), {**COMPANY, "accept_policies": "on"}
    )
    assert response.status_code == 302
    user = User.objects.get(email=COMPANY["email"])
    assert user.policy_version == POLICY_VERSION
    assert user.policy_accepted_at is not None


@pytest.mark.django_db
@pytest.mark.parametrize(
    "url_name", ["core:candidate_signup", "core:company_signup"]
)
def test_signup_form_shows_the_consent_checkbox(client, url_name):
    body = client.get(reverse(url_name)).content.decode()
    assert 'name="accept_policies"' in body
    assert "I agree to the" in body
