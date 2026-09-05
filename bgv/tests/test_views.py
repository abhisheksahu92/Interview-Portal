"""Access rules: feature gate, roles, tenant isolation, token-only consent."""

import json
from decimal import Decimal

import pytest
from django.urls import reverse

from bgv import services
from bgv.models import VerificationOrder
from bgv.tests.conftest import enable_bgv
from billing.models import BillingCharge

pytestmark = pytest.mark.django_db


def _order(company, candidate, package, application=None, owner=None):
    return services.create_order(
        company, candidate, package, application=application, ordered_by=owner
    )


# --- gating ---------------------------------------------------------------- #


def test_feature_gate_blocks_the_workspace(client, owner, company):
    enable_bgv(company, enabled=False)
    client.force_login(owner)
    assert client.get(reverse("bgv:index")).status_code == 403


def test_interviewers_are_not_allowed_in(client, interviewer):
    client.force_login(interviewer)
    assert client.get(reverse("bgv:index")).status_code == 403


def test_anonymous_visitors_are_redirected_or_refused(client):
    assert client.get(reverse("bgv:index")).status_code in (302, 403)


def test_index_lists_orders(client, owner, company, candidate, package, application):
    _order(company, candidate, package, application=application, owner=owner)
    client.force_login(owner)
    response = client.get(reverse("bgv:index"))
    assert response.status_code == 200
    assert b"Awaiting consent" in response.content


def test_status_filter_narrows_the_list(client, owner, company, candidate, package, make_candidate):
    open_order = _order(company, candidate, package, owner=owner)
    done = _order(company, make_candidate("z@example.test"), package, owner=owner)
    services.cancel_order(done)
    client.force_login(owner)
    response = client.get(reverse("bgv:index"), {"status": VerificationOrder.CANCELLED})
    body = response.content.decode()
    assert f"/bgv/orders/{done.pk}/" in body
    assert f"/bgv/orders/{open_order.pk}/" not in body


# --- ordering -------------------------------------------------------------- #


def test_order_create_raises_a_pending_order(client, owner, company, application, package):
    client.force_login(owner)
    response = client.post(
        reverse("bgv:order_create", args=[application.pk]), {"package": package.pk}
    )
    order = VerificationOrder.objects.get(company=company)
    assert response.status_code == 302
    assert order.status == VerificationOrder.CONSENT_PENDING
    assert order.application_id == application.pk
    assert not BillingCharge.objects.exists()


def test_cannot_order_against_another_tenants_application(
    client, other_owner, application, package
):
    client.force_login(other_owner)
    response = client.post(
        reverse("bgv:order_create", args=[application.pk]), {"package": package.pk}
    )
    assert response.status_code == 404


def test_another_tenants_order_is_404(client, other_owner, company, candidate, package, owner):
    order = _order(company, candidate, package, owner=owner)
    client.force_login(other_owner)
    assert client.get(reverse("bgv:order_detail", args=[order.pk])).status_code == 404


def test_cancel_view_cancels_without_charging(client, owner, company, candidate, package):
    order = _order(company, candidate, package, owner=owner)
    client.force_login(owner)
    client.post(reverse("bgv:order_cancel", args=[order.pk]))
    order.refresh_from_db()
    assert order.status == VerificationOrder.CANCELLED
    assert not BillingCharge.objects.exists()


# --- consent (token only) --------------------------------------------------- #


def test_consent_page_needs_no_login(client, company, candidate, package, owner):
    order = _order(company, candidate, package, owner=owner)
    response = client.get(reverse("bgv:consent", args=[order.token]))
    assert response.status_code == 200
    assert b"Employment history" in response.content


def test_unknown_consent_token_is_404(client, db):
    assert client.get(reverse("bgv:consent", args=["not-a-real-token"])).status_code == 404


def test_revoked_consent_token_is_gone(client, company, candidate, package, owner):
    order = _order(company, candidate, package, owner=owner)
    order.revoke()
    assert client.get(reverse("bgv:consent", args=[order.token])).status_code == 410


def test_expired_consent_token_is_gone(client, company, candidate, package, owner):
    from datetime import timedelta

    from django.utils import timezone

    order = _order(company, candidate, package, owner=owner)
    order.expires_at = timezone.now() - timedelta(days=1)
    order.save(update_fields=["expires_at"])
    assert client.get(reverse("bgv:consent", args=[order.token])).status_code == 410


def test_cancelled_order_link_stops_working(client, company, candidate, package, owner):
    order = _order(company, candidate, package, owner=owner)
    services.cancel_order(order)
    assert client.get(reverse("bgv:consent", args=[order.token])).status_code == 410


def test_consent_requires_the_checkbox(client, company, candidate, package, owner):
    order = _order(company, candidate, package, owner=owner)
    response = client.post(
        reverse("bgv:consent", args=[order.token]), {"full_name": "Priya Sharma"}
    )
    order.refresh_from_db()
    assert response.status_code == 200
    assert order.consent_given_at is None
    assert not BillingCharge.objects.exists()


def test_consent_posts_charge_and_submit(client, company, candidate, package, owner):
    order = _order(company, candidate, package, owner=owner)
    response = client.post(
        reverse("bgv:consent", args=[order.token]),
        {"full_name": "Priya Sharma", "agree": "on"},
        REMOTE_ADDR="203.0.113.7",
    )
    order.refresh_from_db()
    assert response.status_code == 302
    assert order.status == VerificationOrder.SUBMITTED
    assert order.consent_ip == "203.0.113.7"
    charge = BillingCharge.objects.get(company=company)
    assert charge.amount_inr == Decimal("1499.00")


def test_reposting_consent_does_not_charge_twice(client, company, candidate, package, owner):
    order = _order(company, candidate, package, owner=owner)
    payload = {"full_name": "Priya Sharma", "agree": "on"}
    url = reverse("bgv:consent", args=[order.token])
    client.post(url, payload)
    client.post(url, payload)
    assert BillingCharge.objects.filter(company=company).count() == 1


# --- report + margin -------------------------------------------------------- #


def test_report_download_is_a_pdf(client, owner, company, candidate, package):
    order = _order(company, candidate, package, owner=owner)
    services.record_consent(order, name="Priya Sharma")
    services.poll_order(order)
    services.poll_order(order)
    client.force_login(owner)
    response = client.get(reverse("bgv:order_report", args=[order.pk]))
    assert response.status_code == 200
    assert response["Content-Type"] == "application/pdf"


def test_margin_page_is_staff_only(client, owner, staff_owner):
    client.force_login(owner)
    assert client.get(reverse("bgv:admin_margin")).status_code == 403
    client.force_login(staff_owner)
    assert client.get(reverse("bgv:admin_margin")).status_code == 200


def test_vendor_cost_is_hidden_from_a_tenant(client, owner, company, candidate, package):
    order = _order(company, candidate, package, owner=owner)
    client.force_login(owner)
    body = client.get(reverse("bgv:order_detail", args=[order.pk])).content.decode()
    assert "1,499" in body
    assert "999" not in body


# --- webhook ---------------------------------------------------------------- #


def _signed(client, payload, key="vendor-secret"):
    from bgv import gateway

    body = json.dumps(payload).encode()
    return client.post(
        reverse("bgv:webhook"),
        data=body,
        content_type="application/json",
        HTTP_X_BGV_SIGNATURE=gateway.sign_payload(body),
    )


def test_webhook_rejects_an_unsigned_body(client, db, settings):
    settings.BGV_API_KEY = "vendor-secret"
    settings.BGV_PROVIDER = "authbridge"
    response = client.post(
        reverse("bgv:webhook"), data=b"{}", content_type="application/json"
    )
    assert response.status_code == 400


def test_webhook_rejects_a_wrong_signature(client, db, settings):
    settings.BGV_API_KEY = "vendor-secret"
    settings.BGV_PROVIDER = "authbridge"
    response = client.post(
        reverse("bgv:webhook"),
        data=b"{}",
        content_type="application/json",
        HTTP_X_BGV_SIGNATURE="deadbeef",
    )
    assert response.status_code == 400


def test_webhook_refuses_everything_on_a_mock_install(client, db, settings):
    settings.BGV_API_KEY = ""
    response = client.post(
        reverse("bgv:webhook"),
        data=b"{}",
        content_type="application/json",
        HTTP_X_BGV_SIGNATURE="anything",
    )
    assert response.status_code == 400


def test_signed_webhook_applies_the_result(client, company, candidate, package, owner, settings):
    order = _order(company, candidate, package, owner=owner)
    services.record_consent(order, name="Priya Sharma")
    settings.BGV_API_KEY = "vendor-secret"
    settings.BGV_PROVIDER = "authbridge"
    response = _signed(
        client,
        {
            "provider_ref": order.provider_ref,
            "state": VerificationOrder.COMPLETED,
            "checks": {"identity": {"status": "DISCREPANCY", "notes": "Name mismatch"}},
        },
    )
    order.refresh_from_db()
    assert response.status_code == 200
    assert order.status == VerificationOrder.COMPLETED
    assert order.has_discrepancy


def test_signed_webhook_for_an_unknown_reference_is_404(client, db, settings):
    settings.BGV_API_KEY = "vendor-secret"
    settings.BGV_PROVIDER = "authbridge"
    assert _signed(client, {"provider_ref": "nope", "state": "COMPLETED"}).status_code == 404
