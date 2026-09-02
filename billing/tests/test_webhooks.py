import json

import pytest
from django.urls import reverse

from billing.models import Plan, Subscription
from billing.services import get_subscription, pro_plan
from billing.webhooks import handle_event


def _post(client, payload, signature="good-signature"):
    return client.post(
        reverse("billing:webhook"),
        data=json.dumps(payload),
        content_type="application/json",
        HTTP_STRIPE_SIGNATURE=signature,
    )


@pytest.fixture
def checkout_completed(company):
    return {
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


def test_checkout_completed_upgrades_to_pro(company, checkout_completed):
    handle_event(checkout_completed)
    subscription = get_subscription(company)
    assert subscription.plan.code == Plan.PRO
    assert subscription.stripe_customer_id == "cus_1"
    assert subscription.stripe_subscription_id == "sub_1"
    assert subscription.status == Subscription.ACTIVE


def test_webhook_endpoint_upgrades_company(client, company, checkout_completed, fake_stripe):
    response = _post(client, checkout_completed)
    assert response.status_code == 200
    assert get_subscription(company).plan.code == Plan.PRO


def test_webhook_bad_signature_returns_400(client, company, checkout_completed, fake_stripe):
    response = _post(client, checkout_completed, signature="forged")
    assert response.status_code == 400
    assert get_subscription(company).plan.code == Plan.FREE


def test_webhook_rejects_get(client, fake_stripe):
    assert client.get(reverse("billing:webhook")).status_code == 405


def test_webhook_without_stripe_configured_returns_503(client, checkout_completed, settings):
    settings.STRIPE_SECRET_KEY = ""
    response = _post(client, checkout_completed)
    assert response.status_code == 503


def test_subscription_updated_past_due(company, checkout_completed):
    handle_event(checkout_completed)
    handle_event(
        {
            "type": "customer.subscription.updated",
            "data": {
                "object": {
                    "object": "subscription",
                    "id": "sub_1",
                    "customer": "cus_1",
                    "status": "past_due",
                    "current_period_end": 1735689600,
                    "items": {"data": [{"price": {"id": "price_pro_123"}}]},
                }
            },
        }
    )
    subscription = get_subscription(company)
    assert subscription.status == Subscription.PAST_DUE
    assert subscription.current_period_end is not None


def test_subscription_deleted_downgrades_to_free(company, checkout_completed):
    handle_event(checkout_completed)
    handle_event(
        {
            "type": "customer.subscription.deleted",
            "data": {"object": {"object": "subscription", "id": "sub_1", "customer": "cus_1"}},
        }
    )
    subscription = get_subscription(company)
    assert subscription.plan.code == Plan.FREE
    assert subscription.status == Subscription.CANCELED
    assert subscription.stripe_subscription_id == ""


def test_subscription_updated_canceled_downgrades_to_free(company, checkout_completed):
    handle_event(checkout_completed)
    handle_event(
        {
            "type": "customer.subscription.updated",
            "data": {
                "object": {
                    "object": "subscription",
                    "id": "sub_1",
                    "customer": "cus_1",
                    "status": "canceled",
                }
            },
        }
    )
    assert get_subscription(company).plan.code == Plan.FREE


def test_invoice_payment_failed_marks_past_due(company, checkout_completed):
    handle_event(checkout_completed)
    handle_event(
        {
            "type": "invoice.payment_failed",
            "data": {"object": {"object": "invoice", "customer": "cus_1"}},
        }
    )
    assert get_subscription(company).status == Subscription.PAST_DUE


def test_unhandled_event_is_ignored(company, checkout_completed):
    assert handle_event({"type": "ping", "data": {"object": {}}}) is None


def test_unknown_customer_is_ignored(db):
    event = {
        "type": "invoice.payment_failed",
        "data": {"object": {"object": "invoice", "customer": "cus_nope"}},
    }
    assert handle_event(event) is None


def test_price_id_maps_to_plan(company, checkout_completed):
    plan = pro_plan()
    plan.stripe_price_id = "price_mapped"
    plan.save()
    handle_event(checkout_completed)
    handle_event(
        {
            "type": "customer.subscription.updated",
            "data": {
                "object": {
                    "object": "subscription",
                    "id": "sub_1",
                    "customer": "cus_1",
                    "status": "active",
                    "items": {"data": [{"price": {"id": "price_mapped"}}]},
                }
            },
        }
    )
    assert get_subscription(company).plan.stripe_price_id == "price_mapped"
