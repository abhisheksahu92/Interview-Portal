import pytest
from django.urls import reverse

from billing.models import Plan, Subscription
from billing.services import get_subscription
from jobs.models import Job

pytestmark = pytest.mark.django_db


def test_overview_shows_plan_and_usage(client, owner, company):
    Job.objects.create(company=company, title="Dev 1", status=Job.OPEN)
    client.force_login(owner)
    response = client.get(reverse("billing:overview"))
    assert response.status_code == 200
    assert response.context["open_jobs"] == 1
    assert response.context["max_open_jobs"] == 1
    assert response.context["plan"].code == Plan.FREE
    assert b"Upgrade to Pro" in response.content


def test_overview_creates_free_subscription(client, owner, company):
    client.force_login(owner)
    client.get(reverse("billing:overview"))
    assert Subscription.objects.get(company=company).plan.code == Plan.FREE


def test_overview_requires_login(client):
    response = client.get(reverse("billing:overview"))
    assert response.status_code == 302


def test_recruiter_can_view_overview(client, recruiter):
    client.force_login(recruiter)
    response = client.get(reverse("billing:overview"))
    assert response.status_code == 200
    assert response.context["is_owner"] is False


def test_checkout_redirects_to_stripe(client, owner, company, fake_stripe):
    client.force_login(owner)
    response = client.post(reverse("billing:checkout"))
    assert response.status_code == 302
    assert response["Location"] == "https://stripe.test/session"
    call = fake_stripe.checkout.Session.calls[-1]
    assert call["line_items"][0]["price"] == "price_pro_123"
    assert call["client_reference_id"] == str(company.pk)


def test_checkout_requires_post(client, owner, fake_stripe):
    client.force_login(owner)
    assert client.get(reverse("billing:checkout")).status_code == 405


def test_non_owner_cannot_checkout(client, recruiter, fake_stripe):
    client.force_login(recruiter)
    assert client.post(reverse("billing:checkout")).status_code == 403


def test_non_owner_cannot_open_portal(client, recruiter, fake_stripe):
    client.force_login(recruiter)
    assert client.post(reverse("billing:portal")).status_code == 403


def test_checkout_without_stripe_configured_redirects_with_message(client, owner, settings):
    settings.STRIPE_SECRET_KEY = ""
    settings.STRIPE_PRICE_ID_PRO = ""
    client.force_login(owner)
    response = client.post(reverse("billing:checkout"), follow=True)
    assert response.status_code == 200
    assert any("Stripe is not configured" in str(m) for m in response.context["messages"])


def test_portal_redirects_to_stripe(client, owner, company, fake_stripe):
    subscription = get_subscription(company)
    subscription.stripe_customer_id = "cus_1"
    subscription.save()
    client.force_login(owner)
    response = client.post(reverse("billing:portal"))
    assert response.status_code == 302
    assert response["Location"] == "https://stripe.test/session"
    assert fake_stripe.billing_portal.Session.calls[-1]["customer"] == "cus_1"


def test_portal_without_customer_redirects_back(client, owner, fake_stripe):
    client.force_login(owner)
    response = client.post(reverse("billing:portal"))
    assert response.status_code == 302
    assert response["Location"] == reverse("billing:overview")


def test_nav_shows_billing_link_and_plan_badge(client, owner, company):
    get_subscription(company)
    client.force_login(owner)
    response = client.get(reverse("web:dashboard"))
    assert response.status_code == 200
    assert reverse("billing:overview").encode() in response.content
    assert b">Free</span>" in response.content
