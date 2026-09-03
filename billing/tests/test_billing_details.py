"""GSTIN + billing-address validation and the derived place of supply."""

import pytest
from django.urls import reverse

from billing.forms import BillingDetailsForm
from billing.invoicing import gst_split
from billing.services import get_subscription

pytestmark = pytest.mark.django_db

GOOD = {
    "gstin": "29abcde1234f1z5",
    "line1": "12 MG Road",
    "city": "Bengaluru",
    "state": "Karnataka",
    "pincode": "560001",
}


def test_gstin_is_optional():
    form = BillingDetailsForm({**GOOD, "gstin": ""})
    assert form.is_valid(), form.errors
    assert form.cleaned_data["gstin"] == ""
    assert form.billing_address()["state_code"] == ""


@pytest.mark.parametrize(
    "bad",
    ["29ABCDE1234F1Z", "ABCDE1234F1Z5XX", "29ABCDE1234F1A5", "290BCDE1234F1Z5"],
)
def test_bad_gstin_is_rejected(bad):
    form = BillingDetailsForm({**GOOD, "gstin": bad})
    assert not form.is_valid()
    assert "gstin" in form.errors


def test_good_gstin_is_uppercased_and_yields_a_state_code():
    form = BillingDetailsForm(GOOD)
    assert form.is_valid(), form.errors
    assert form.cleaned_data["gstin"] == "29ABCDE1234F1Z5"
    assert form.state_code == "29"
    assert form.billing_address()["state_code"] == "29"


def test_address_fields_are_required():
    form = BillingDetailsForm({"gstin": ""})
    assert not form.is_valid()
    assert {"line1", "city", "state", "pincode"} <= set(form.errors)


@pytest.mark.parametrize("bad", ["56001", "5600011", "abc123", "060001x"])
def test_pincode_must_be_six_digits(bad):
    form = BillingDetailsForm({**GOOD, "pincode": bad})
    assert not form.is_valid()
    assert "pincode" in form.errors


def test_view_saves_details_and_derives_state_code(client, owner, company):
    client.force_login(owner)
    response = client.post(reverse("billing:details"), GOOD)
    assert response.status_code == 302
    subscription = get_subscription(company)
    assert subscription.gstin == "29ABCDE1234F1Z5"
    assert subscription.billing_address["state_code"] == "29"
    assert subscription.billing_address["pincode"] == "560001"


def test_view_renders_errors_inline(client, owner, company):
    client.force_login(owner)
    response = client.post(reverse("billing:details"), {**GOOD, "gstin": "nope"})
    assert response.status_code == 400
    assert response.context["details_form"].errors["gstin"]
    assert b"valid 15-character GSTIN" in response.content
    assert get_subscription(company).gstin == ""


def test_gst_split_uses_the_derived_state_code(client, owner, company, settings):
    settings.COMPANY_STATE_CODE = "29"
    client.force_login(owner)
    client.post(reverse("billing:details"), GOOD)
    subscription = get_subscription(company)
    assert subscription.billing_state_code == "29"
    cgst, sgst, igst = gst_split(1000, subscription.billing_state_code)
    assert (cgst, sgst) == (90, 90) and igst == 0

    client.post(reverse("billing:details"), {**GOOD, "gstin": "27ABCDE1234F1Z5"})
    subscription.refresh_from_db()
    assert subscription.billing_state_code == "27"
    cgst, sgst, igst = gst_split(1000, subscription.billing_state_code)
    assert (cgst, sgst) == (0, 0) and igst == 180
