"""Recruiter-facing form for the careers site editor."""

from django import forms

from careers.models import CareersSite


class CareersSiteForm(forms.ModelForm):
    class Meta:
        model = CareersSite
        fields = [
            "slug",
            "custom_domain",
            "headline",
            "about",
            "brand_color",
            "logo",
            "hero_image",
            "seo_title",
            "seo_description",
            "show_salary",
        ]
        widgets = {
            "slug": forms.TextInput(attrs={"class": "form-control"}),
            "custom_domain": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "careers.example.com"}
            ),
            "headline": forms.TextInput(attrs={"class": "form-control"}),
            "about": forms.Textarea(attrs={"class": "form-control", "rows": 8}),
            "brand_color": forms.TextInput(attrs={"class": "form-control form-control-color",
                                                  "type": "color"}),
            "seo_title": forms.TextInput(attrs={"class": "form-control"}),
            "seo_description": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            "show_salary": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def clean_custom_domain(self):
        domain = (self.cleaned_data.get("custom_domain") or "").strip().lower()
        if not domain:
            return None
        if "/" in domain or " " in domain:
            raise forms.ValidationError("Enter a bare hostname, without scheme or path.")
        return domain
