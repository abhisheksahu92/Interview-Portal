import pytest
from django.test import override_settings
from django.urls import reverse

from core.models import Company, Membership, User
from partners.models import Referral, Reseller
from partners.referral import COOKIE_NAME, attach_referral, capture_ref

MIDDLEWARE_WITH_REFERRAL = [
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "core.middleware.TenantMiddleware",
    "partners.middleware.ReferralMiddleware",
]


@pytest.fixture
def reseller(db):
    return Reseller.objects.create(name="Partner One", code="partner1", commission_pct=25)


def test_referral_link_sets_cookie_and_redirects(client, reseller):
    response = client.get(reverse("partners:referral_link", args=[reseller.code]))
    assert response.status_code == 302
    assert reverse("core:company_signup") in response["Location"]
    assert client.cookies[COOKIE_NAME].value == "partner1"


def test_referral_link_unknown_code_404s(client, db):
    assert client.get("/partners/r/nope/").status_code == 404


def test_capture_ref_prefers_query_then_cookie(rf, reseller):
    request = rf.get("/", {"ref": "PARTNER1"})
    request.session = {}
    assert capture_ref(request) == "partner1"
    assert request.session["ip_ref"] == "partner1"

    request = rf.get("/")
    request.COOKIES[COOKIE_NAME] = "partner1"
    request.session = {}
    assert capture_ref(request) == "partner1"


def test_attach_referral_ignores_unknown_and_inactive(db, reseller):
    company = Company.objects.create(name="Solo")
    assert attach_referral(company, code="missing") is None
    reseller.active = False
    reseller.save()
    assert attach_referral(company, code=reseller.code) is None


def test_attach_referral_is_idempotent(db, reseller):
    company = Company.objects.create(name="Solo")
    first = attach_referral(company, code=reseller.code)
    assert attach_referral(company, code=reseller.code).pk == first.pk


@override_settings(MIDDLEWARE=MIDDLEWARE_WITH_REFERRAL)
def test_cookie_referral_attaches_on_company_signup(client, reseller):
    """End to end: referral link -> cookie -> middleware -> OWNER membership."""
    client.get(reverse("partners:referral_link", args=[reseller.code]))
    response = client.post(
        reverse("core:company_signup"),
        {
            "company_name": "Referred Co",
            "email": "founder@referred.test",
            "password1": "sup3rsecret!x",
            "password2": "sup3rsecret!x",
            "accept_policies": "on",
        },
    )
    assert response.status_code in (200, 302)
    company = Company.objects.get(name="Referred Co")
    assert Membership.objects.filter(company=company, role=Membership.OWNER).exists()
    referral = Referral.objects.get(company=company)
    assert referral.reseller == reseller


@override_settings(MIDDLEWARE=MIDDLEWARE_WITH_REFERRAL)
def test_membership_without_referral_creates_nothing(client, db):
    company = Company.objects.create(name="Organic Co")
    user = User.objects.create_user(email="organic@test.test", password="pw12345678")
    Membership.objects.create(user=user, company=company, role=Membership.OWNER)
    assert not Referral.objects.filter(company=company).exists()
