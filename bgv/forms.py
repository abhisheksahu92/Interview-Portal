"""Forms for ordering a check and for the candidate's consent page."""

from django import forms

from bgv.models import CheckPackage, VerificationOrder


class OrderForm(forms.Form):
    """Package chooser shown to the recruiter."""

    package = forms.ModelChoiceField(
        queryset=CheckPackage.objects.none(),
        empty_label=None,
        widget=forms.RadioSelect,
        label="Verification package",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["package"].queryset = CheckPackage.objects.filter(active=True)


class ConsentForm(forms.Form):
    """The candidate's authorisation. Both fields are legally load-bearing."""

    full_name = forms.CharField(
        max_length=150,
        label="Type your full name",
        widget=forms.TextInput(attrs={"autocomplete": "name", "class": "form-control"}),
    )
    agree = forms.BooleanField(
        label="I authorise these checks to be carried out on me.",
        error_messages={"required": "You must tick the box to authorise the checks."},
    )

    def __init__(self, *args, order=None, **kwargs):
        self.order = order
        super().__init__(*args, **kwargs)

    def clean_full_name(self):
        name = (self.cleaned_data["full_name"] or "").strip()
        if len(name) < 2:
            raise forms.ValidationError("Enter your full name as it appears on your ID.")
        return name


class OrderFilterForm(forms.Form):
    """Status filter on the orders list."""

    status = forms.ChoiceField(
        required=False,
        choices=[("", "All statuses"), *VerificationOrder.STATUS_CHOICES],
        widget=forms.Select(attrs={"class": "form-select form-select-sm"}),
    )
