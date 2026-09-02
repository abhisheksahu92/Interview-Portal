import pytest
from django.db import IntegrityError

from core.models import Company, Membership, User


@pytest.mark.django_db
def test_company_autoslug_is_unique():
    a = Company.objects.create(name="Acme Corp")
    b = Company.objects.create(name="Acme Corp")
    assert a.slug == "acme-corp"
    assert b.slug == "acme-corp-2"


@pytest.mark.django_db
def test_user_created_with_email_only():
    user = User.objects.create_user(email="a@example.com", password="pw12345678")
    assert user.get_username() == "a@example.com"
    assert user.username == ""
    assert user.is_candidate is False
    assert User.USERNAME_FIELD == "email"


@pytest.mark.django_db
def test_email_is_unique():
    User.objects.create_user(email="dup@example.com", password="pw12345678")
    with pytest.raises(IntegrityError):
        User.objects.create_user(email="dup@example.com", password="pw12345678")


@pytest.mark.django_db
def test_superuser_flags():
    su = User.objects.create_superuser(email="su@example.com", password="pw12345678")
    assert su.is_staff and su.is_superuser


@pytest.mark.django_db
def test_membership_unique_per_user_and_company():
    company = Company.objects.create(name="Acme")
    user = User.objects.create_user(email="m@example.com", password="pw12345678")
    Membership.objects.create(user=user, company=company, role=Membership.OWNER)
    with pytest.raises(IntegrityError):
        Membership.objects.create(user=user, company=company, role=Membership.RECRUITER)


@pytest.mark.django_db
def test_role_helpers():
    company = Company.objects.create(name="Acme")
    other = Company.objects.create(name="Other")
    user = User.objects.create_user(email="r@example.com", password="pw12345678")
    Membership.objects.create(user=user, company=company, role=Membership.INTERVIEWER)
    assert user.role_in(company) == Membership.INTERVIEWER
    assert user.role_in(other) is None
    assert user.role_in(None) is None
    assert list(user.companies) == [company]
