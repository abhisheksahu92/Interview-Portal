"""Emails are stored and matched case-insensitively."""

import pytest
from django.urls import reverse

from core.models import Company, Invitation, Membership, User


@pytest.mark.django_db
def test_create_user_lowercases_email():
    user = User.objects.create_user(email="Foo@X.Com", password="pw12345!")
    assert user.email == "foo@x.com"


@pytest.mark.django_db
def test_save_lowercases_email():
    user = User(email="  MiXeD@Example.COM  ")
    user.set_password("pw12345!")
    user.save()
    assert User.objects.get(pk=user.pk).email == "mixed@example.com"


@pytest.mark.django_db
def test_candidate_signup_rejects_case_variant_duplicate(client):
    User.objects.create_user(email="Foo@X.com", password="pw12345!")
    resp = client.post(
        reverse("core:candidate_signup"),
        {
            "email": "foo@x.com",
            "password1": "sup3r-secret-pw",
            "password2": "sup3r-secret-pw",
        },
    )
    assert resp.status_code == 200
    assert "email" in resp.context["form"].errors
    assert User.objects.count() == 1


@pytest.mark.django_db
def test_company_signup_lowercases_email(client):
    resp = client.post(
        reverse("core:company_signup"),
        {
            "company_name": "Widgets Ltd",
            "email": "Owner@Widgets.COM",
            "password1": "sup3r-secret-pw",
            "password2": "sup3r-secret-pw",
        },
    )
    assert resp.status_code == 302
    assert User.objects.filter(email="owner@widgets.com").exists()


@pytest.mark.django_db
def test_login_with_mixed_case_email_works(client):
    User.objects.create_user(email="user@example.com", password="pw12345!")
    resp = client.post(
        reverse("core:login"),
        {"username": "USER@Example.com", "password": "pw12345!"},
    )
    assert resp.status_code == 302
    assert client.session.get("_auth_user_id")


@pytest.mark.django_db
def test_login_matches_a_legacy_mixed_case_row(client):
    user = User.objects.create_user(email="legacy@example.com", password="pw12345!")
    # Simulate a row written before normalisation.
    User.objects.filter(pk=user.pk).update(email="Legacy@Example.com")
    resp = client.post(
        reverse("core:login"),
        {"username": "legacy@example.com", "password": "pw12345!"},
    )
    assert resp.status_code == 302
    assert client.session.get("_auth_user_id") == str(user.pk)


@pytest.mark.django_db
def test_invitation_email_is_lowercased_and_matches_user():
    company = Company.objects.create(name="Acme")
    invitation = Invitation.objects.create(company=company, email="New@Person.IO")
    assert invitation.email == "new@person.io"

    user = User.objects.create_user(email="NEW@person.io", password="pw12345!")
    assert user.email == invitation.email
    invitation.accept(user)
    assert Membership.objects.filter(user=user, company=company).exists()
