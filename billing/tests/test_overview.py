"""The redesigned billing overview: provider choice, meters, trial, GST form."""

import pytest
from django.urls import reverse

from billing import invoicing
from billing.models import Plan, Subscription
from billing.services import get_subscription
from billing.views import provider_choice

pytestmark = pytest.mark.django_db


def test_razorpay_is_the_default_provider(settings):
    settings.RAZORPAY_KEY_ID = "rzp_test"
    settings.RAZORPAY_KEY_SECRET = "secret"
    settings.STRIPE_SECRET_KEY = "sk_test"
    assert provider_choice() == Subscription.RAZORPAY


def test_stripe_is_used_when_only_stripe_is_configured(settings, monkeypatch):
    settings.RAZORPAY_KEY_ID = ""
    settings.RAZORPAY_KEY_SECRET = ""
    monkeypatch.setattr("billing.gateway.is_configured", lambda: True)
    assert provider_choice() == Subscription.STRIPE


def test_no_provider_when_neither_is_configured(settings, monkeypatch):
    settings.RAZORPAY_KEY_ID = ""
    settings.RAZORPAY_KEY_SECRET = ""
    monkeypatch.setattr("billing.gateway.is_configured", lambda: False)
    assert provider_choice() == ""


def test_overview_shows_the_not_configured_state(client, owner, settings, monkeypatch):
    settings.RAZORPAY_KEY_ID = ""
    settings.RAZORPAY_KEY_SECRET = ""
    monkeypatch.setattr("billing.gateway.is_configured", lambda: False)
    client.force_login(owner)
    response = client.get(reverse("billing:overview"))
    assert response.context["not_configured"] is True
    assert b"No payment provider is configured" in response.content


def test_overview_offers_razorpay_buttons(client, owner, settings):
    settings.RAZORPAY_KEY_ID = "rzp_test"
    settings.RAZORPAY_KEY_SECRET = "secret"
    client.force_login(owner)
    response = client.get(reverse("billing:overview"))
    assert response.context["provider"] == Subscription.RAZORPAY
    assert b"Pay with Razorpay" in response.content
    assert reverse("billing:razorpay_checkout").encode() in response.content


def test_overview_lists_the_three_tiers_with_inr_prices(client, owner):
    client.force_login(owner)
    response = client.get(reverse("billing:overview"))
    codes = [p.code for p in response.context["plans"]]
    assert codes == [Plan.STARTER, Plan.GROWTH, Plan.AGENCY]
    assert b"1499" in response.content
    assert b"12999" in response.content


def test_yearly_toggle_switches_the_prices(client, owner):
    client.force_login(owner)
    response = client.get(reverse("billing:overview") + "?interval=YEARLY")
    assert response.context["interval"] == Subscription.YEARLY
    assert b"129990" in response.content


def test_overview_shows_the_trial_banner(client, db, trial_company):
    from core.models import Membership, User

    user = User.objects.create_user(email="own@fresh.test", password="pw12345678")
    Membership.objects.create(user=user, company=trial_company, role=Membership.OWNER)
    client.force_login(user)
    response = client.get(reverse("billing:overview"))
    assert response.context["in_trial"] is True
    assert response.context["trial_days_left"] >= 13
    assert b"Free trial" in response.content


def test_overview_shows_usage_meters_and_seats(client, owner, company):
    client.force_login(owner)
    response = client.get(reverse("billing:overview"))
    kinds = [row["kind"] for row in response.context["usage_rows"]]
    assert kinds == ["AI_SCREEN", "WHATSAPP_MSG", "VIDEO_MINUTE"]
    assert response.context["seats_used"] == 1
    assert response.context["max_seats"] == Plan.objects.get(code=Plan.FREE).max_seats
    assert b"Monthly usage" in response.content


def test_overview_lists_invoices(client, owner, company):
    invoice = invoicing.create_invoice(company, 4999, with_pdf=False)
    client.force_login(owner)
    response = client.get(reverse("billing:overview"))
    assert response.context["invoices"] == [invoice]
    assert invoice.number.encode() in response.content


def test_owner_can_save_gstin_and_billing_address(client, owner, company):
    client.force_login(owner)
    response = client.post(
        reverse("billing:details"),
        {
            "gstin": "27aaaaa0000a1z5",
            "line1": "1 Fergusson Road",
            "city": "Pune",
            "state": "Maharashtra",
            "pincode": "411004",
        },
        follow=True,
    )
    assert response.status_code == 200
    subscription = get_subscription(company)
    assert subscription.gstin == "27AAAAA0000A1Z5"
    assert subscription.billing_state_code == "27"
    assert subscription.billing_address["city"] == "Pune"


def test_recruiter_cannot_save_billing_details(client, recruiter):
    client.force_login(recruiter)
    assert client.post(reverse("billing:details")).status_code == 403


def test_recruiter_sees_a_read_only_overview(client, recruiter):
    client.force_login(recruiter)
    response = client.get(reverse("billing:overview"))
    assert response.context["is_owner"] is False
    assert b"Only the company owner can" in response.content
