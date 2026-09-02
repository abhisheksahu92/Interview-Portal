import pytest
from django.core.exceptions import PermissionDenied
from django.test import RequestFactory

from core.models import Company, Membership, User
from core.permissions import for_company, role_required


@pytest.mark.django_db
def test_for_company_scopes_and_blocks_none():
    a = Company.objects.create(name="A")
    b = Company.objects.create(name="B")
    ua = User.objects.create_user(email="a@x.com", password="pw12345678")
    ub = User.objects.create_user(email="b@x.com", password="pw12345678")
    Membership.objects.create(user=ua, company=a, role=Membership.OWNER)
    Membership.objects.create(user=ub, company=b, role=Membership.OWNER)

    qs = Membership.objects.all()
    assert list(for_company(qs, a)) == list(Membership.objects.filter(company=a))
    assert for_company(qs, None).count() == 0


@pytest.mark.django_db
def test_role_required_allows_and_denies():
    company = Company.objects.create(name="A")
    owner = User.objects.create_user(email="o@x.com", password="pw12345678")
    Membership.objects.create(user=owner, company=company, role=Membership.OWNER)

    @role_required(Membership.OWNER)
    def view(request):
        return "ok"

    request = RequestFactory().get("/")
    request.user = owner
    request.company = company
    assert view(request) == "ok"

    interviewer = User.objects.create_user(email="i@x.com", password="pw12345678")
    Membership.objects.create(user=interviewer, company=company, role=Membership.INTERVIEWER)
    request.user = interviewer
    with pytest.raises(PermissionDenied):
        view(request)


@pytest.mark.django_db
def test_role_required_needs_company():
    user = User.objects.create_user(email="n@x.com", password="pw12345678")

    @role_required(Membership.OWNER)
    def view(request):
        return "ok"

    request = RequestFactory().get("/")
    request.user = user
    request.company = None
    with pytest.raises(PermissionDenied):
        view(request)
