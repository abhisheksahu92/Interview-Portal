"""Forms for offer templates, offer creation and candidate signing."""

import json

from django import forms
from django.utils import timezone

from offers.models import Offer, OfferTemplate


def _bs(widget_attrs=None, css="form-control"):
    attrs = {"class": css}
    attrs.update(widget_attrs or {})
    return attrs


class OfferTemplateForm(forms.ModelForm):
    class Meta:
        model = OfferTemplate
        fields = ["name", "subject", "body_html", "is_default"]
        widgets = {
            "name": forms.TextInput(attrs=_bs()),
            "subject": forms.TextInput(attrs=_bs()),
            "body_html": forms.Textarea(attrs=_bs({"rows": 18, "spellcheck": "false"})),
            "is_default": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.company = company

    def clean_name(self):
        name = (self.cleaned_data["name"] or "").strip()
        company = self.company or getattr(self.instance, "company_id", None) and self.instance.company
        if company is not None:
            clash = OfferTemplate.objects.filter(company=company, name__iexact=name)
            if self.instance.pk:
                clash = clash.exclude(pk=self.instance.pk)
            if clash.exists():
                raise forms.ValidationError("A template with this name already exists.")
        return name

    def save(self, commit=True):
        template = super().save(commit=False)
        if self.company is not None:
            template.company = self.company
        if commit:
            template.save()
        return template


class OfferForm(forms.ModelForm):
    custom_fields_text = forms.CharField(
        label="Custom fields (JSON)",
        required=False,
        help_text='e.g. {"bonus": "10% annual"} — use them as {{custom.bonus}}.',
        widget=forms.Textarea(attrs=_bs({"rows": 3, "spellcheck": "false"})),
    )

    class Meta:
        model = Offer
        fields = ["template", "salary", "currency", "joining_date", "expires_at"]
        widgets = {
            "template": forms.Select(attrs=_bs(css="form-select")),
            "salary": forms.NumberInput(attrs=_bs({"step": "0.01", "min": "0"})),
            "currency": forms.TextInput(attrs=_bs({"maxlength": 8})),
            "joining_date": forms.DateInput(attrs=_bs({"type": "date"}), format="%Y-%m-%d"),
            "expires_at": forms.DateTimeInput(
                attrs=_bs({"type": "datetime-local"}), format="%Y-%m-%dT%H:%M"
            ),
        }

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.company = company
        self.fields["template"].queryset = OfferTemplate.objects.for_company(company)
        self.fields["template"].required = False
        self.fields["template"].empty_label = "Company default template"
        if self.instance.pk and self.instance.custom_fields:
            self.initial.setdefault(
                "custom_fields_text", json.dumps(self.instance.custom_fields, indent=2)
            )

    def clean_custom_fields_text(self):
        raw = (self.cleaned_data.get("custom_fields_text") or "").strip()
        if not raw:
            return {}
        try:
            parsed = json.loads(raw)
        except ValueError:
            raise forms.ValidationError("Enter valid JSON, e.g. {\"bonus\": \"10%\"}.") from None
        if not isinstance(parsed, dict):
            raise forms.ValidationError("Custom fields must be a JSON object.")
        return {str(key): value for key, value in parsed.items()}

    def clean_expires_at(self):
        expires_at = self.cleaned_data.get("expires_at")
        if expires_at and expires_at <= timezone.now():
            raise forms.ValidationError("Pick an expiry in the future.")
        return expires_at

    def save(self, commit=True):
        offer = super().save(commit=False)
        offer.custom_fields = self.cleaned_data.get("custom_fields_text") or {}
        if commit:
            offer.save()
        return offer


class SignForm(forms.Form):
    signed_name = forms.CharField(
        label="Type your full name to sign",
        max_length=150,
        widget=forms.TextInput(attrs=_bs({"autocomplete": "name"})),
    )
    consent = forms.BooleanField(
        label="I have read the offer and agree that typing my name is my electronic signature.",
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )

    def __init__(self, *args, expected_name="", **kwargs):
        super().__init__(*args, **kwargs)
        self.expected_name = (expected_name or "").strip()

    def clean_signed_name(self):
        name = (self.cleaned_data["signed_name"] or "").strip()
        if len(name.split()) < 1 or len(name) < 2:
            raise forms.ValidationError("Enter your full name as it appears on the offer.")
        return name


class DeclineForm(forms.Form):
    decline_reason = forms.CharField(
        label="Reason (optional)",
        required=False,
        widget=forms.Textarea(attrs=_bs({"rows": 3})),
    )
