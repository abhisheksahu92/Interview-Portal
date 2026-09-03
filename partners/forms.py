"""Forms for branding and reseller management."""

from django import forms

from partners.models import Reseller, WhiteLabel
from partners.whitelabel import safe_color


class WhiteLabelForm(forms.ModelForm):
    class Meta:
        model = WhiteLabel
        fields = [
            "brand_name",
            "logo",
            "primary_color",
            "custom_domain",
            "hide_powered_by",
            "email_from_name",
        ]
        widgets = {
            "brand_name": forms.TextInput(attrs={"class": "form-control"}),
            "logo": forms.ClearableFileInput(attrs={"class": "form-control"}),
            "primary_color": forms.TextInput(attrs={"class": "form-control", "type": "color"}),
            "custom_domain": forms.TextInput(attrs={"class": "form-control"}),
            "email_from_name": forms.TextInput(attrs={"class": "form-control"}),
            "hide_powered_by": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def clean_primary_color(self):
        value = (self.cleaned_data.get("primary_color") or "").strip()
        if value and safe_color(value) != value:
            raise forms.ValidationError("Use a hex colour such as #4f46e5.")
        return value


class ResellerForm(forms.ModelForm):
    class Meta:
        model = Reseller
        fields = ["name", "code", "contact_email", "commission_pct", "active"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "code": forms.TextInput(attrs={"class": "form-control"}),
            "contact_email": forms.EmailInput(attrs={"class": "form-control"}),
            "commission_pct": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }
