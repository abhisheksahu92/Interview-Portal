"""Billing identity form: GSTIN and the Indian billing address.

The GSTIN carries the customer's state in its first two digits, and that state
code is what :func:`billing.invoicing.gst_split` uses to decide CGST+SGST vs
IGST — so it is *derived* here rather than typed by hand.
"""

import re

from django import forms

#: 15-character GSTIN: state code, PAN, entity number, "Z", checksum.
GSTIN_RE = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$")

PINCODE_RE = re.compile(r"^[1-9][0-9]{5}$")

#: Valid GST state codes are 01-38 (plus 97 "other territory", 99 "centre").
VALID_STATE_CODES = {f"{n:02d}" for n in range(1, 39)} | {"97", "99"}


def _bs(attrs=None):
    base = {"class": "form-control form-control-sm"}
    base.update(attrs or {})
    return base


class BillingDetailsForm(forms.Form):
    """GSTIN + billing address, saved onto the company's Subscription."""

    gstin = forms.CharField(
        required=False,
        max_length=20,
        label="GSTIN",
        widget=forms.TextInput(attrs=_bs({"placeholder": "29ABCDE1234F1Z5"})),
    )
    line1 = forms.CharField(max_length=200, label="Address line 1", widget=forms.TextInput(attrs=_bs()))
    line2 = forms.CharField(
        required=False, max_length=200, label="Address line 2", widget=forms.TextInput(attrs=_bs())
    )
    city = forms.CharField(max_length=80, label="City", widget=forms.TextInput(attrs=_bs()))
    state = forms.CharField(max_length=80, label="State", widget=forms.TextInput(attrs=_bs()))
    pincode = forms.CharField(
        max_length=6,
        label="PIN code",
        widget=forms.TextInput(attrs=_bs({"inputmode": "numeric", "maxlength": "6"})),
    )
    country = forms.CharField(
        required=False, max_length=80, label="Country", widget=forms.TextInput(attrs=_bs())
    )

    def clean_gstin(self):
        value = (self.cleaned_data.get("gstin") or "").strip().upper()
        if not value:
            return ""
        if not GSTIN_RE.match(value):
            raise forms.ValidationError(
                "Enter a valid 15-character GSTIN, e.g. 29ABCDE1234F1Z5."
            )
        if value[:2] not in VALID_STATE_CODES:
            raise forms.ValidationError(f"{value[:2]} is not a valid GST state code.")
        return value

    def clean_pincode(self):
        value = (self.cleaned_data.get("pincode") or "").strip()
        if not PINCODE_RE.match(value):
            raise forms.ValidationError("Enter a 6-digit PIN code.")
        return value

    @property
    def state_code(self):
        """State code derived from the GSTIN (blank when there is no GSTIN)."""
        gstin = (self.cleaned_data or {}).get("gstin") or ""
        return gstin[:2]

    def billing_address(self):
        """The JSON blob stored on ``Subscription.billing_address``."""
        data = self.cleaned_data
        return {
            "line1": data["line1"].strip(),
            "line2": (data.get("line2") or "").strip(),
            "city": data["city"].strip(),
            "state": data["state"].strip(),
            "state_code": self.state_code,
            "pincode": data["pincode"],
            "postal_code": data["pincode"],  # legacy key kept for old templates
            "country": (data.get("country") or "India").strip() or "India",
        }

    def apply_to(self, subscription):
        """Persist the cleaned values onto ``subscription``."""
        subscription.gstin = self.cleaned_data["gstin"]
        subscription.billing_address = self.billing_address()
        subscription.save(update_fields=["gstin", "billing_address", "updated_at"])
        return subscription

    @classmethod
    def from_subscription(cls, subscription):
        """An unbound form pre-filled from a stored subscription."""
        address = subscription.billing_address or {}
        return cls(
            initial={
                "gstin": subscription.gstin,
                "line1": address.get("line1", ""),
                "line2": address.get("line2", ""),
                "city": address.get("city", ""),
                "state": address.get("state", ""),
                "pincode": address.get("pincode") or address.get("postal_code") or "",
                "country": address.get("country", "India"),
            }
        )
