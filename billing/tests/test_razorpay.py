"""Razorpay: checkout creation, signature verification and webhooks (mocked)."""

import hashlib
import hmac
import json

import pytest
from django.urls import reverse

from billing import razorpay_gateway
from billing.models import Invoice, PendingCheckout, Plan, Subscription
from billing.services import get_subscription
from billing.webhooks import handle_razorpay_event

pytestmark = pytest.mark.django_db


def _post_webhook(client, payload, secret="rzp_hook_secret", signature=None):
    body = json.dumps(payload).encode()
    if signature is None:
        signature = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return client.post(
        reverse("billing:razorpay_webhook"),
        data=body,
        content_type="application/json",
        HTTP_X_RAZORPAY_SIGNATURE=signature,
    )


def _event(name, company, plan_code=Plan.GROWTH, **extra):
    payload = {
        "subscription": {
            "entity": {
                "id": "sub_rzp_1",
                "notes": {"company_id": str(company.pk), "plan_code": plan_code},
            }
        },
        "payment": {"entity": {"id": "pay_rzp_1", "amount": 499900}},
    }
    payload.update(extra)
    return {"event": name, "payload": payload}


# --- configuration --------------------------------------------------------


def test_not_configured_without_keys(settings):
    settings.RAZORPAY_KEY_ID = ""
    settings.RAZORPAY_KEY_SECRET = ""
    assert razorpay_gateway.is_configured() is False
    with pytest.raises(razorpay_gateway.RazorpayUnavailable):
        razorpay_gateway.get_client()


# --- signatures -----------------------------------------------------------


def test_order_payment_signature_verifies(settings):
    settings.RAZORPAY_KEY_SECRET = "secret"
    signature = hmac.new(b"secret", b"order_1|pay_1", hashlib.sha256).hexdigest()
    assert razorpay_gateway.verify_payment_signature(
        order_id="order_1", payment_id="pay_1", signature=signature
    )


def test_subscription_payment_signature_verifies(settings):
    settings.RAZORPAY_KEY_SECRET = "secret"
    signature = hmac.new(b"secret", b"pay_1|sub_1", hashlib.sha256).hexdigest()
    assert razorpay_gateway.verify_payment_signature(
        payment_id="pay_1", signature=signature, subscription_id="sub_1"
    )


def test_bad_payment_signature_is_rejected(settings):
    settings.RAZORPAY_KEY_SECRET = "secret"
    with pytest.raises(razorpay_gateway.SignatureInvalid):
        razorpay_gateway.verify_payment_signature(
            order_id="order_1", payment_id="pay_1", signature="nope"
        )


def test_webhook_signature_verifies(settings):
    settings.RAZORPAY_WEBHOOK_SECRET = "hook"
    body = b'{"event":"payment.failed"}'
    signature = hmac.new(b"hook", body, hashlib.sha256).hexdigest()
    assert razorpay_gateway.verify_webhook_signature(body, signature)
    with pytest.raises(razorpay_gateway.SignatureInvalid):
        razorpay_gateway.verify_webhook_signature(body, "nope")


# --- checkout -------------------------------------------------------------


def test_monthly_checkout_creates_a_razorpay_subscription(client, owner, company, fake_razorpay):
    client.force_login(owner)
    response = client.post(
        reverse("billing:razorpay_checkout"), {"plan": Plan.GROWTH, "interval": "MONTHLY"}
    )
    assert response.status_code == 200
    assert response.context["is_subscription"] is True
    assert response.context["options"]["subscription_id"] == "sub_test_1"
    assert response.context["options"]["key"] == "rzp_test_key"
    kinds = [name for name, _ in fake_razorpay.calls]
    assert "subscription" in kinds  # and a plan was created lazily
    assert "plan" in kinds
    assert get_subscription(company).razorpay_subscription_id == "sub_test_1"


def test_yearly_checkout_creates_a_one_time_order(client, owner, company, fake_razorpay):
    client.force_login(owner)
    response = client.post(
        reverse("billing:razorpay_checkout"), {"plan": Plan.AGENCY, "interval": "YEARLY"}
    )
    assert response.status_code == 200
    assert response.context["is_subscription"] is False
    options = response.context["options"]
    assert options["order_id"] == "order_test_1"
    assert options["amount"] == 12999000  # 129990 INR in paise
    assert get_subscription(company).interval == Subscription.YEARLY


def test_checkout_without_keys_redirects_with_a_message(client, owner, settings):
    settings.RAZORPAY_KEY_ID = ""
    settings.RAZORPAY_KEY_SECRET = ""
    client.force_login(owner)
    response = client.post(reverse("billing:razorpay_checkout"), {"plan": Plan.GROWTH}, follow=True)
    assert any("Razorpay is not configured" in str(m) for m in response.context["messages"])


def test_non_owner_cannot_start_razorpay_checkout(client, recruiter, fake_razorpay):
    client.force_login(recruiter)
    assert client.post(reverse("billing:razorpay_checkout")).status_code == 403


def test_verify_activates_the_plan(client, owner, company, settings):
    settings.RAZORPAY_KEY_SECRET = "secret"
    signature = hmac.new(b"secret", b"pay_1|sub_1", hashlib.sha256).hexdigest()
    # The plan now comes from the checkout we recorded before redirecting, not
    # from the POST — a caller cannot name their own tier on the way back.
    PendingCheckout.objects.create(
        company=company,
        remote_id="sub_1",
        plan=Plan.objects.get(code=Plan.GROWTH),
        interval=Subscription.MONTHLY,
    )
    client.force_login(owner)
    response = client.post(
        reverse("billing:razorpay_verify"),
        {
            "plan": Plan.GROWTH,
            "razorpay_payment_id": "pay_1",
            "razorpay_subscription_id": "sub_1",
            "razorpay_signature": signature,
        },
    )
    assert response.status_code == 200
    assert response.json()["ok"] is True
    subscription = get_subscription(company)
    assert subscription.plan.code == Plan.GROWTH
    assert subscription.status == Subscription.ACTIVE
    assert subscription.provider == Subscription.RAZORPAY


def test_verify_rejects_a_forged_signature(client, owner, company, settings):
    settings.RAZORPAY_KEY_SECRET = "secret"
    client.force_login(owner)
    response = client.post(
        reverse("billing:razorpay_verify"),
        {
            "plan": Plan.GROWTH,
            "razorpay_payment_id": "pay_1",
            "razorpay_order_id": "order_1",
            "razorpay_signature": "forged",
        },
    )
    assert response.status_code == 400
    assert get_subscription(company).plan.code == Plan.FREE


# --- webhooks -------------------------------------------------------------


def test_webhook_rejects_a_bad_signature(client, company, settings):
    settings.RAZORPAY_WEBHOOK_SECRET = "rzp_hook_secret"
    response = _post_webhook(client, _event("subscription.activated", company), signature="bad")
    assert response.status_code == 400
    assert get_subscription(company).plan.code == Plan.FREE


def test_webhook_without_secret_returns_503(client, company, settings):
    settings.RAZORPAY_WEBHOOK_SECRET = ""
    assert _post_webhook(client, _event("subscription.activated", company)).status_code == 503


def test_webhook_rejects_get(client, settings):
    settings.RAZORPAY_WEBHOOK_SECRET = "rzp_hook_secret"
    assert client.get(reverse("billing:razorpay_webhook")).status_code == 405


def test_webhook_activates_the_subscription(client, company, settings):
    settings.RAZORPAY_WEBHOOK_SECRET = "rzp_hook_secret"
    response = _post_webhook(client, _event("subscription.activated", company))
    assert response.status_code == 200
    subscription = get_subscription(company)
    assert subscription.plan.code == Plan.GROWTH
    assert subscription.status == Subscription.ACTIVE
    assert subscription.razorpay_subscription_id == "sub_rzp_1"


def test_subscription_charged_issues_an_invoice(company):
    handle_razorpay_event(_event("subscription.charged", company))
    invoice = Invoice.objects.get(company=company)
    assert invoice.number.startswith("IP/")
    assert invoice.amount == Plan.objects.get(code=Plan.GROWTH).price_monthly_inr
    assert invoice.provider == Subscription.RAZORPAY
    assert invoice.provider_ref == "pay_rzp_1"
    assert invoice.paid_at is not None


def test_subscription_halted_marks_past_due(company):
    handle_razorpay_event(_event("subscription.halted", company))
    subscription = get_subscription(company)
    assert subscription.status == Subscription.PAST_DUE
    assert subscription.past_due_since is not None


def test_payment_failed_marks_past_due(company):
    handle_razorpay_event(_event("payment.failed", company))
    assert get_subscription(company).status == Subscription.PAST_DUE


def test_subscription_cancelled_downgrades_to_free(company):
    handle_razorpay_event(_event("subscription.activated", company))
    handle_razorpay_event(_event("subscription.cancelled", company))
    subscription = get_subscription(company)
    assert subscription.plan.code == Plan.FREE
    assert subscription.status == Subscription.CANCELED
    assert subscription.razorpay_subscription_id == ""


def test_unknown_event_and_unknown_company_are_ignored(company):
    assert handle_razorpay_event(_event("subscription.pending", company)) is None
    orphan = {"event": "subscription.charged", "payload": {"subscription": {"entity": {}}}}
    assert handle_razorpay_event(orphan) is None


@pytest.mark.django_db
def test_verify_ignores_the_plan_in_the_post_body(client, owner, company, settings):
    """The exploit: pay ₹999 for STARTER, come back claiming AGENCY.

    The callback signature only proves the payment belongs to the order, so the
    tier must come from the checkout we recorded before redirecting.
    """
    settings.RAZORPAY_KEY_SECRET = "secret"
    signature = hmac.new(b"secret", b"pay_2|sub_2", hashlib.sha256).hexdigest()
    PendingCheckout.objects.create(
        company=company,
        remote_id="sub_2",
        plan=Plan.objects.get(code=Plan.STARTER),
        interval=Subscription.MONTHLY,
    )
    client.force_login(owner)

    response = client.post(
        reverse("billing:razorpay_verify"),
        {
            "plan": Plan.AGENCY,
            "razorpay_payment_id": "pay_2",
            "razorpay_subscription_id": "sub_2",
            "razorpay_signature": signature,
        },
    )

    assert response.status_code == 200
    assert get_subscription(company).plan.code == Plan.STARTER


@pytest.mark.django_db
def test_a_replayed_callback_cannot_activate_twice(client, owner, company, settings):
    settings.RAZORPAY_KEY_SECRET = "secret"
    signature = hmac.new(b"secret", b"pay_3|sub_3", hashlib.sha256).hexdigest()
    PendingCheckout.objects.create(
        company=company,
        remote_id="sub_3",
        plan=Plan.objects.get(code=Plan.GROWTH),
        interval=Subscription.MONTHLY,
    )
    client.force_login(owner)
    payload = {
        "razorpay_payment_id": "pay_3",
        "razorpay_subscription_id": "sub_3",
        "razorpay_signature": signature,
    }

    first = client.post(reverse("billing:razorpay_verify"), payload)
    second = client.post(reverse("billing:razorpay_verify"), payload)

    assert first.status_code == 200
    assert second.status_code == 400


@pytest.mark.django_db
def test_another_companys_checkout_cannot_be_claimed(client, owner, company, settings):
    """A valid triple from any company on the merchant account used to work."""
    settings.RAZORPAY_KEY_SECRET = "secret"
    signature = hmac.new(b"secret", b"pay_4|sub_4", hashlib.sha256).hexdigest()
    from core.models import Company

    other_company = Company.objects.create(name="Rival Staffing")
    PendingCheckout.objects.create(
        company=other_company,
        remote_id="sub_4",
        plan=Plan.objects.get(code=Plan.AGENCY),
        interval=Subscription.MONTHLY,
    )
    client.force_login(owner)

    response = client.post(
        reverse("billing:razorpay_verify"),
        {
            "razorpay_payment_id": "pay_4",
            "razorpay_subscription_id": "sub_4",
            "razorpay_signature": signature,
        },
    )

    assert response.status_code == 400
    assert get_subscription(company).plan.code != Plan.AGENCY
