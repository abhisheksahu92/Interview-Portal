"""Forms for the seeker portal.

The mailbox form is the only interesting one: the password never round-trips to
the browser, so an empty password field means "keep the stored one" rather than
"clear it".
"""

from django import forms

from seeker.models import SeekerProfile


class PreferencesForm(forms.ModelForm):
    target_roles_text = forms.CharField(
        label="Target roles",
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "Backend engineer, Django developer"}),
        help_text="Comma separated.",
    )

    class Meta:
        model = SeekerProfile
        fields = ["min_budget_inr", "remote_only"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields["target_roles_text"].initial = ", ".join(self.instance.target_roles or [])
        for field in self.fields.values():
            css = (
                "form-check-input"
                if isinstance(field.widget, forms.CheckboxInput)
                else "form-control"
            )
            field.widget.attrs.setdefault("class", css)

    def save(self, commit=True):
        profile = super().save(commit=False)
        raw = self.cleaned_data.get("target_roles_text") or ""
        profile.target_roles = [part.strip() for part in raw.split(",") if part.strip()]
        if commit:
            profile.save()
        return profile


class SMTPMailboxForm(forms.Form):
    """SMTP app-password settings. Blank password keeps whatever is stored."""

    mailbox_email = forms.EmailField(label="Your address")
    host = forms.CharField(label="SMTP host", max_length=200)
    port = forms.IntegerField(label="Port", min_value=1, max_value=65535, initial=587)
    username = forms.CharField(label="Username", max_length=200)
    password = forms.CharField(
        label="App password",
        required=False,
        widget=forms.PasswordInput(render_value=False),
        help_text="Leave blank to keep the password already saved.",
    )
    use_ssl = forms.BooleanField(label="Connect over SSL (port 465)", required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            css = (
                "form-check-input"
                if isinstance(field.widget, forms.CheckboxInput)
                else "form-control"
            )
            field.widget.attrs.setdefault("class", css)


class AddLeadForm(forms.Form):
    """Paste a posting we are not allowed to fetch ourselves."""

    url = forms.URLField(label="Link", required=False, assume_scheme="https")
    title = forms.CharField(label="Role", max_length=300, required=False)
    company = forms.CharField(label="Company", max_length=200, required=False)
    text = forms.CharField(
        label="Pasted text",
        widget=forms.Textarea(attrs={"rows": 8}),
        help_text="We store the first 600 characters and the link, nothing more.",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-control")

    def clean(self):
        data = super().clean()
        if not data.get("url") and not data.get("text"):
            raise forms.ValidationError("Paste the posting text or its link.")
        return data


class DraftForm(forms.Form):
    """One editable draft on the compose page."""

    outreach_id = forms.IntegerField(widget=forms.HiddenInput)
    to_email = forms.EmailField()
    subject = forms.CharField(max_length=300)
    body = forms.CharField(widget=forms.Textarea(attrs={"rows": 10}))
