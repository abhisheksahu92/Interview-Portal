import pytest
from django.test import RequestFactory

from core.middleware import TenantMiddleware
from core.models import Company, Membership, User


def _run(request):
    middleware = TenantMiddleware(lambda r: r)
    middleware(request)
    return request.company


class AnonymousStub:
    is_authenticated = False


@pytest.fixture
def factory():
    return RequestFactory()


@pytest.mark.django_db
def test_anonymous_gets_no_company(factory):
    request = factory.get("/")
    request.user = AnonymousStub()
    request.session = {}
    assert _run(request) is None


@pytest.mark.django_db
def test_falls_back_to_first_membership(factory):
    company = Company.objects.create(name="A")
    user = User.objects.create_user(email="u@x.com", password="pw12345678")
    Membership.objects.create(user=user, company=company, role=Membership.OWNER)

    request = factory.get("/")
    request.user = user
    request.session = {}
    assert _run(request) == company
    assert request.session["company_id"] == company.id


@pytest.mark.django_db
def test_session_company_wins(factory):
    a = Company.objects.create(name="A")
    b = Company.objects.create(name="B")
    user = User.objects.create_user(email="u@x.com", password="pw12345678")
    Membership.objects.create(user=user, company=a, role=Membership.OWNER)
    Membership.objects.create(user=user, company=b, role=Membership.RECRUITER)

    request = factory.get("/")
    request.user = user
    request.session = {"company_id": b.id}
    assert _run(request) == b


@pytest.mark.django_db
def test_stale_or_foreign_session_company_is_dropped(factory):
    a = Company.objects.create(name="A")
    foreign = Company.objects.create(name="Foreign")
    user = User.objects.create_user(email="u@x.com", password="pw12345678")
    Membership.objects.create(user=user, company=a, role=Membership.OWNER)

    request = factory.get("/")
    request.user = user
    request.session = {"company_id": foreign.id}
    assert _run(request) == a


@pytest.mark.django_db
def test_user_without_membership_gets_none(factory):
    user = User.objects.create_user(
        email="c@x.com", password="pw12345678", is_candidate=True
    )
    request = factory.get("/")
    request.user = user
    request.session = {}
    assert _run(request) is None
