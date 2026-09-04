"""Forms for the integrations UI."""

from django import forms

from integrations.connectors import adapter_class
from integrations.events import EVENT_CHOICES
from integrations.models import ConnectorConfig, OutboundWebhook


class BootstrapMixin:
    """Apply Bootstrap classes without hand-writing widgets everywhere."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, forms.CheckboxInput | forms.CheckboxSelectMultiple):
                continue
            classes = widget.attrs.get("class", "")
            widget.attrs["class"] = f"{classes} form-control".strip()


class WebhookForm(BootstrapMixin, forms.ModelForm):
    """Create/edit an outbound webhook.

    ``events`` is a JSONField on the model but a checkbox list in the UI; an
    empty selection means "every event", which is what an empty list means to
    :meth:`OutboundWebhook.subscribes_to`.
    """

    events = forms.MultipleChoiceField(
        choices=EVENT_CHOICES,
        required=False,
        widget=forms.CheckboxSelectMultiple,
        help_text="Leave everything unchecked to receive all events.",
    )

    #: declared explicitly so the scheme default is pinned rather than inherited
    #: from the deprecated global default.
    url = forms.URLField(
        assume_scheme="https",
        max_length=500,
        widget=forms.URLInput(attrs={"placeholder": "https://example.com/hooks/ip"}),
    )

    class Meta:
        model = OutboundWebhook
        fields = ["name", "url", "events", "active"]

    def __init__(self, *args, **kwargs):
        self.company = kwargs.pop("company", None)
        super().__init__(*args, **kwargs)
        self.fields["active"].widget.attrs["class"] = "form-check-input"
        if self.instance.pk and not self.is_bound:
            self.initial["events"] = self.instance.events or []

    def clean_url(self):
        url = self.cleaned_data["url"].strip()
        if not url.lower().startswith(("http://", "https://")):
            raise forms.ValidationError("Enter an http(s) URL.")
        return url

    def clean_events(self):
        return list(self.cleaned_data.get("events") or [])

    def save(self, commit=True):
        webhook = super().save(commit=False)
        if self.company is not None:
            webhook.company = self.company
        if commit:
            webhook.save()
        return webhook


class ConnectorForm(BootstrapMixin, forms.Form):
    """Per-connector credential form, built from the adapter's settings keys.

    Secret values are rendered masked: the field is left blank with the masked
    current value as its placeholder, and submitting it blank keeps the stored
    secret rather than wiping it.
    """

    active = forms.BooleanField(required=False, label="Enabled")

    def __init__(self, *args, **kwargs):
        self.config = kwargs.pop("config")
        super().__init__(*args, **kwargs)
        self.adapter_cls = adapter_class(self.config.kind)
        stored = self.config.settings or {}
        for key in self.adapter_cls.setting_fields():
            is_secret = key in self.adapter_cls.secret_settings
            required = key in self.adapter_cls.required_settings and not is_secret
            self.fields[key] = forms.CharField(
                required=required,
                label=key.replace("_", " ").title(),
                widget=forms.TextInput(
                    attrs={
                        "class": "form-control",
                        "placeholder": (
                            self.masked(stored.get(key)) if is_secret else ""
                        ),
                        "autocomplete": "off",
                    }
                ),
            )
            if not is_secret:
                self.fields[key].initial = stored.get(key, "")
        self.fields["active"].widget.attrs["class"] = "form-check-input"
        self.fields["active"].initial = self.config.active

    @staticmethod
    def masked(value):
        if not value:
            return ""
        value = str(value)
        return f"{'•' * 8}{value[-4:]}" if len(value) > 4 else "•" * len(value)

    def apply(self):
        """Merge the submitted values into the stored (encrypted) settings."""
        stored = dict(self.config.settings or {})
        for key in self.adapter_cls.setting_fields():
            value = (self.cleaned_data.get(key) or "").strip()
            if not value and key in self.adapter_cls.secret_settings:
                continue  # blank secret = keep what we have
            if value:
                stored[key] = value
            else:
                stored.pop(key, None)
        self.config.settings = stored
        self.config.active = bool(self.cleaned_data.get("active"))
        self.config.save(update_fields=["settings", "active", "updated_at"])
        return self.config


def connector_configs(company):
    """A ConnectorConfig row per known kind, creating placeholders as needed."""
    existing = {c.kind: c for c in ConnectorConfig.objects.for_company(company)}
    configs = []
    for kind, _label in ConnectorConfig.KIND_CHOICES:
        config = existing.get(kind)
        if config is None:
            config = ConnectorConfig(company=company, kind=kind, settings={}, active=False)
        configs.append(config)
    return configs
