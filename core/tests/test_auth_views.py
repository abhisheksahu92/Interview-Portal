import pytest
from django.urls import reverse

from core.models import Company, Membership, User


@pytest.mark.django_db
def test_login_page_renders(client):
    response = client.get(reverse("core:login"))
    assert response.status_code == 200
    assert b"Sign in" in response.content


@pytest.mark.django_db
def test_login_with_email(client):
    User.objects.create_user(email="u@x.com", password="pw12345678")
    response = client.post(
        reverse("core:login"), {"username": "u@x.com", "password": "pw12345678"}
    )
    assert response.status_code == 302
    assert client.session.get("_auth_user_id")


@pytest.mark.django_db
def test_candidate_signup_creates_candidate(client):
    response = client.post(
        reverse("core:candidate_signup"),
        {
            "email": "cand@x.com",
            "password1": "sup3r-secret-pw",
            "password2": "sup3r-secret-pw",
            "accept_policies": "on",
        },
    )
    assert response.status_code == 302
    user = User.objects.get(email="cand@x.com")
    assert user.is_candidate is True
    assert user.memberships.count() == 0


@pytest.mark.django_db
def test_company_signup_creates_company_owner_and_session(client):
    response = client.post(
        reverse("core:company_signup"),
        {
            "company_name": "Acme Staffing",
            "email": "own@x.com",
            "password1": "sup3r-secret-pw",
            "password2": "sup3r-secret-pw",
            "accept_policies": "on",
        },
    )
    assert response.status_code == 302
    company = Company.objects.get(name="Acme Staffing")
    user = User.objects.get(email="own@x.com")
    assert user.is_candidate is False
    assert user.role_in(company) == Membership.OWNER
    assert client.session["company_id"] == company.id


@pytest.mark.django_db
def test_switch_company(client):
    a = Company.objects.create(name="A")
    b = Company.objects.create(name="B")
    user = User.objects.create_user(email="u@x.com", password="pw12345678")
    Membership.objects.create(user=user, company=a, role=Membership.OWNER)
    Membership.objects.create(user=user, company=b, role=Membership.RECRUITER)
    client.force_login(user)

    response = client.post(reverse("core:switch_company"), {"company_id": b.id})
    assert response.status_code == 302
    assert client.session["company_id"] == b.id


@pytest.mark.django_db
def test_switch_company_rejects_non_member(client):
    a = Company.objects.create(name="A")
    foreign = Company.objects.create(name="Foreign")
    user = User.objects.create_user(email="u@x.com", password="pw12345678")
    Membership.objects.create(user=user, company=a, role=Membership.OWNER)
    client.force_login(user)

    client.post(reverse("core:switch_company"), {"company_id": foreign.id})
    assert client.session["company_id"] == a.id


@pytest.mark.django_db
def test_logout(client):
    user = User.objects.create_user(email="u@x.com", password="pw12345678")
    client.force_login(user)
    response = client.post(reverse("core:logout"))
    assert response.status_code == 302
    assert not client.session.get("_auth_user_id")


@pytest.mark.django_db
def test_account_home_requires_login(client):
    response = client.get(reverse("core:account_home"))
    assert response.status_code == 302
    assert reverse("core:login") in response.url


@pytest.mark.django_db
def test_seed_demo_command():
    from django.core.management import call_command

    call_command("seed_demo", verbosity=0)
    company = Company.objects.get(name="Demo Staffing")
    # 3 team members + 1 demo candidate + 3 applicants
    assert User.objects.count() == 7
    owner = User.objects.get(email="owner@demo.test")
    assert owner.check_password("demo1234")
    assert owner.role_in(company) == Membership.OWNER
    assert company.jobs.count() == 2
    assert company.skills.count() == 3
    assert company.questions.count() == 3

    # Re-running must be idempotent, not a crash or a duplicate.
    call_command("seed_demo", verbosity=0)
    assert User.objects.count() == 7
    assert company.jobs.count() == 2


def test_healthz_needs_no_auth_or_database(client):
    """The container/Fly/Railway probe: no login, no tenant, no DB access."""
    response = client.get("/healthz/")
    assert response.status_code == 200
    assert response.content == b"ok"
