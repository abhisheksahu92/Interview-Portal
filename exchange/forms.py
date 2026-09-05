"""Forms for publishing requirements, filtering the feed and submitting."""

from django import forms

from core.permissions import for_company
from exchange.models import ExchangeRequirement
from jobs.models import Job, Skill


class FeedFilterForm(forms.Form):
    """Skills / location / budget filters on the exchange feed."""

    q = forms.CharField(
        required=False,
        label="Search",
        widget=forms.TextInput(
            attrs={"class": "form-control", "placeholder": "Role or keyword", "autocomplete": "off"}
        ),
    )
    skills = forms.ModelMultipleChoiceField(
        queryset=Skill.objects.none(),
        required=False,
        widget=forms.SelectMultiple(attrs={"class": "form-select", "size": 6}),
    )
    location = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Pune, remote"}),
    )
    budget_min = forms.DecimalField(
        required=False,
        min_value=0,
        label="Budget at least (₹)",
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "10000"}),
    )

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["skills"].queryset = for_company(Skill.objects.all(), company).order_by("name")

    def criteria(self):
        data = self.cleaned_data if self.is_bound and self.is_valid() else {}
        return {
            "query": data.get("q") or "",
            "skills": list(data.get("skills") or []),
            "location": data.get("location") or "",
            "budget_min": data.get("budget_min"),
        }


class PublishRequirementForm(forms.Form):
    """Publish one of your OPEN jobs to the exchange."""

    job = forms.ModelChoiceField(
        queryset=Job.objects.none(),
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    title = forms.CharField(
        max_length=200,
        required=False,
        help_text="Defaults to the job title.",
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    client_name = forms.CharField(
        max_length=150,
        required=False,
        label="End client",
        help_text="Anonymised for anyone who is not an accepted partner.",
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    location = forms.CharField(
        max_length=150, required=False, widget=forms.TextInput(attrs={"class": "form-control"})
    )
    skills = forms.ModelMultipleChoiceField(
        queryset=Skill.objects.none(),
        required=False,
        help_text="Defaults to the job's skills.",
        widget=forms.SelectMultiple(attrs={"class": "form-select", "size": 6}),
    )
    budget_ctc_min = forms.DecimalField(
        required=False,
        min_value=0,
        label="Budget min (₹)",
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "10000"}),
    )
    budget_ctc_max = forms.DecimalField(
        required=False,
        min_value=0,
        label="Budget max (₹)",
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "10000"}),
    )
    fee_split_pct = forms.IntegerField(
        min_value=0,
        max_value=100,
        initial=50,
        label="Partner's fee split (%)",
        widget=forms.NumberInput(attrs={"class": "form-control"}),
    )
    visibility = forms.ChoiceField(
        choices=ExchangeRequirement.VISIBILITY_CHOICES,
        initial=ExchangeRequirement.PARTNERS,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    expires_in_days = forms.IntegerField(
        min_value=1,
        max_value=180,
        initial=30,
        label="Expires in (days)",
        widget=forms.NumberInput(attrs={"class": "form-control"}),
    )

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["job"].queryset = for_company(Job.objects.all(), company).exclude(
            status=Job.CLOSED
        )
        self.fields["skills"].queryset = for_company(Skill.objects.all(), company).order_by("name")

    def clean(self):
        data = super().clean()
        low, high = data.get("budget_ctc_min"), data.get("budget_ctc_max")
        if low is not None and high is not None and high < low:
            self.add_error("budget_ctc_max", "Maximum budget cannot be below the minimum.")
        return data


class SubmitCandidateForm(forms.Form):
    """Pick a candidate from your talent pool to offer against a requirement."""

    talent_profile = forms.ModelChoiceField(
        queryset=None,
        label="Candidate",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    note = forms.CharField(
        required=False,
        label="Note to the partner",
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 3}),
    )

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        from talent.models import TalentProfile

        self.fields["talent_profile"].queryset = for_company(
            TalentProfile.objects.all(), company
        ).order_by("name", "email")


class PartnerInviteForm(forms.Form):
    """Invite by company slug or the email of one of its owners."""

    target = forms.CharField(
        max_length=254,
        label="Company slug or owner email",
        widget=forms.TextInput(
            attrs={"class": "form-control", "placeholder": "acme-staffing or owner@acme.test"}
        ),
    )


class HireForm(forms.Form):
    """Record the agreed placement fee for a hired submission."""

    placement_fee_inr = forms.DecimalField(
        min_value=1,
        label="Placement fee (₹)",
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "1000"}),
    )


class DisputeForm(forms.Form):
    reason = forms.CharField(
        label="What is wrong?",
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 3}),
    )
