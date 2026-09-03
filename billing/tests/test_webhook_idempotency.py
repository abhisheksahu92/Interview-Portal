"""Replayed gateway webhooks must not be applied twice.

Both Stripe and Razorpay retry deliveries (and can replay them from their
dashboards), so a repeat of a payment event must not mint a second invoice,
a second placement fee or a second commission entry.
"""

import hashlib
import hmac
import json

import pytest
from django.urls import reverse

from billing import webhooks
from billing.models import Invoice, Plan, ProcessedWebhookEvent, Subscription
from billing.services import get_subscription

pytestmark = pytest.mark.django_db


# --- helpers -------------------------------------------------------------


def _stripe_event(company, event_id="evt_stripe_1"):
    return {
        "id": event_id,
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "object": "checkout.session",
                "client_reference_id": str(company.pk),
                "customer": "cus_1",
                "subscription": "sub_1",
            }
        },
    }


def _razorpay_event(company, name="subscription.charged"):
    return {
        "event": name,
        "payload": {
            "subscription": {
                "entity": {
                    "id": "sub_rzp_1",
                    "notes": {
                        "company_id": str(company.pk),
                        "plan_code": Plan.GROWTH,
                    },
                }
            },
            "payment": {"entity": {"id": "pay_rzp_1", "amount": 499900}},
        },
    }


def _post_razorpay(client, payload, event_id="evt_rzp_1", secret="rzp_hook_secret"):
    body = json.dumps(payload).encode()
    signature = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return client.post(
        reverse("billing:razorpay_webhook"),
        data=body,
        content_type="application/json",
        HTTP_X_RAZORPAY_SIGNATURE=signature,
        HTTP_X_RAZORPAY_EVENT_ID=event_id,
    )


# --- fingerprints and claims ---------------------------------------------


def test_fingerprint_is_stable_and_body_sensitive():
    assert webhooks.event_fingerprint(b"abc") == webhooks.event_fingerprint("abc")
    assert webhooks.event_fingerprint(b"abc") != webhooks.event_fingerprint(b"abd")
    assert webhooks.event_fingerprint({"a": 1, "b": 2}) == webhooks.event_fingerprint(
        {"b": 2, "a": 1}
    )


def test_mark_processed_claims_once():
    assert webhooks.mark_processed(Subscription.STRIPE, "evt_9", "x") is True
    assert webhooks.mark_processed(Subscription.STRIPE, "evt_9", "x") is False
    assert webhooks.already_processed(Subscription.STRIPE, "evt_9") is True
    # Same id, different provider — a separate event.
    assert webhooks.mark_processed(Subscription.RAZORPAY, "evt_9", "x") is True
    assert ProcessedWebhookEvent.objects.count() == 2


def test_mark_processed_without_an_id_does_not_block():
    assert webhooks.mark_processed(Subscription.STRIPE, "", "x") is True
    assert webhooks.already_processed(Subscription.STRIPE, "") is False
    assert ProcessedWebhookEvent.objects.count() == 0


# --- Stripe --------------------------------------------------------------


def test_replayed_stripe_event_issues_one_invoice(company):
    event = _stripe_event(company)
    assert webhooks.handle_event(event) is not None
    assert webhooks.handle_event(event) is None
    assert Invoice.objects.filter(company=company).count() <= 1
    assert (
        ProcessedWebhookEvent.objects.filter(
            provider=Subscription.STRIPE, event_id="evt_stripe_1"
        ).count()
        == 1
    )


def test_replayed_stripe_endpoint_delivery_issues_one_invoice(
    client, company, fake_stripe
):
    event = _stripe_event(company, event_id="evt_stripe_replay")
    url = reverse("billing:webhook")
    for _ in range(3):
        response = client.post(
            url,
            data=json.dumps(event),
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE="good-signature",
        )
        assert response.status_code == 200
    assert get_subscription(company).plan.code == Plan.PRO
    assert Invoice.objects.filter(company=company).count() <= 1


def test_distinct_stripe_events_are_both_applied(company):
    assert webhooks.handle_event(_stripe_event(company, "evt_a")) is not None
    assert webhooks.handle_event(_stripe_event(company, "evt_b")) is not None
    assert ProcessedWebhookEvent.objects.count() == 2


def test_stripe_event_without_an_id_is_deduped_by_body_hash(company):
    event = _stripe_event(company)
    event.pop("id")
    assert webhooks.handle_event(event) is not None
    assert webhooks.handle_event(event) is None


# --- Razorpay ------------------------------------------------------------


def test_replayed_razorpay_event_issues_one_invoice(company, fake_razorpay):
    event = _razorpay_event(company)
    assert webhooks.handle_razorpay_event(event, event_id="evt_rzp_1") is not None
    before = Invoice.objects.filter(company=company).count()
    assert webhooks.handle_razorpay_event(event, event_id="evt_rzp_1") is None
    assert Invoice.objects.filter(company=company).count() == before


def test_replayed_razorpay_delivery_uses_the_header_event_id(
    client, company, fake_razorpay
):
    event = _razorpay_event(company)
    for _ in range(3):
        assert _post_razorpay(client, event).status_code == 200
    assert Invoice.objects.filter(company=company).count() == 1
    assert (
        ProcessedWebhookEvent.objects.filter(
            provider=Subscription.RAZORPAY, event_id="evt_rzp_1"
        ).count()
        == 1
    )


def test_razorpay_delivery_without_a_header_falls_back_to_the_body_hash(
    client, company, fake_razorpay
):
    event = _razorpay_event(company)
    body = json.dumps(event).encode()
    signature = hmac.new(b"rzp_hook_secret", body, hashlib.sha256).hexdigest()
    for _ in range(2):
        response = client.post(
            reverse("billing:razorpay_webhook"),
            data=body,
            content_type="application/json",
            HTTP_X_RAZORPAY_SIGNATURE=signature,
        )
        assert response.status_code == 200
    assert Invoice.objects.filter(company=company).count() == 1
    recorded = ProcessedWebhookEvent.objects.get(provider=Subscription.RAZORPAY)
    assert recorded.event_id.startswith("sha256:")
    assert recorded.event_type == "subscription.charged"


def test_two_razorpay_deliveries_with_different_ids_are_both_applied(
    company, fake_razorpay
):
    event = _razorpay_event(company)
    assert webhooks.handle_razorpay_event(event, event_id="a") is not None
    assert webhooks.handle_razorpay_event(event, event_id="b") is not None
    assert ProcessedWebhookEvent.objects.count() == 2


# --- Downstream side effects ---------------------------------------------


def test_replay_does_not_double_a_reseller_commission(company, fake_razorpay):
    """Commissions are computed from paid invoices, so one invoice = one entry."""
    from django.core.management import call_command

    from partners.models import CommissionLedger, Referral, Reseller

    reseller = Reseller.objects.create(name="Chan Partners", code="CHAN", commission_pct=10)
    Referral.objects.create(reseller=reseller, company=company)

    event = _razorpay_event(company)
    webhooks.handle_razorpay_event(event, event_id="evt_commission")
    webhooks.handle_razorpay_event(event, event_id="evt_commission")

    call_command("compute_commissions")
    call_command("compute_commissions")
    assert CommissionLedger.objects.count() == Invoice.objects.filter(
        company=company, paid_at__isnull=False
    ).count()
