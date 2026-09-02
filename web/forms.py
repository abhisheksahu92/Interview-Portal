"""Forms for the web UI. All model access goes through jobs/assessments models."""

from django import forms

from core.models import Invitation, Membership
from jobs.models import CandidateProfile, Job, PipelineStage, Skill, StageReview


class BootstrapMixin:
    """Add Bootstrap classes to every widget."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, forms.CheckboxInput):
                widget.attrs.setdefault("class", "form-check-input")
            elif isinstance(widget, forms.SelectMultiple):
                widget.attrs.setdefault("class", "form-select")
                widget.attrs.setdefault("size", "6")
            elif isinstance(widget, forms.Select):
                widget.attrs.setdefault("class", "form-select")
            else:
                widget.attrs.setdefault("class", "form-control")


class JobForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = Job
        fields = [
            "title",
            "location",
            "employment_type",
            "status",
            "description",
            "requirements",
            "skills",
            "closes_at",
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 5}),
            "requirements": forms.Textarea(attrs={"rows": 5}),
            "closes_at": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.company = company
        self.fields["skills"].queryset = Skill.objects.filter(company=company)
        self.fields["skills"].required = False

    def save(self, commit=True):
        job = super().save(commit=False)
        if self.company is not None:
            job.company = self.company
        if commit:
            job.save()
            self.save_m2m()
        return job


class StageForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = PipelineStage
        fields = ["name", "order", "kind", "requires_assessment"]


class ReviewForm(BootstrapMixin, forms.Form):
    """A stage review: decision + optional rating and feedback."""

    DECISION_CHOICES = [("", "Choose…"), *StageReview.DECISION_CHOICES]

    decision = forms.ChoiceField(choices=DECISION_CHOICES)
    rating = forms.TypedChoiceField(
        choices=[("", "—")] + [(i, f"{i}/5") for i in range(1, 6)],
        coerce=int,
        required=False,
        empty_value=None,
    )
    feedback = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 3}), required=False
    )


class SkillForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = Skill
        fields = ["name"]

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.company = company

    def save(self, commit=True):
        skill = super().save(commit=False)
        skill.company = self.company
        if commit:
            skill.save()
        return skill


class InviteForm(BootstrapMixin, forms.Form):
    """Create a pending core.Invitation for an email address."""

    email = forms.EmailField()
    role = forms.ChoiceField(choices=Membership.ROLE_CHOICES)

    def __init__(self, *args, company=None, invited_by=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.company = company
        self.invited_by = invited_by

    def clean_email(self):
        return self.cleaned_data["email"].strip().lower()

    def clean(self):
        cleaned = super().clean()
        email = cleaned.get("email")
        if email and self.company is not None:
            if Membership.objects.filter(
                company=self.company, user__email__iexact=email
            ).exists():
                self.add_error("email", "That person is already a member.")
        return cleaned

    def save(self):
        """Create (or refresh) the invitation.

        An existing account for the address is fine: we still send an invite
        rather than silently adding them to the company.
        """
        email = self.cleaned_data["email"]
        role = self.cleaned_data["role"]
        invitation = Invitation.objects.filter(
            company=self.company, email=email, accepted_at__isnull=True
        ).first()
        if invitation is None:
            invitation = Invitation.objects.create(
                company=self.company,
                email=email,
                role=role,
                invited_by=self.invited_by,
            )
        else:
            invitation.role = role
            invitation.token = Invitation.new_token()
            invitation.expires_at = Invitation.default_expiry()
            invitation.save(update_fields=["role", "token", "expires_at"])
        return invitation


class CandidateProfileForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = CandidateProfile
        fields = [
            "headline",
            "phone",
            "date_of_birth",
            "experience_years",
            "notice_period_days",
            "resume",
            "skills",
        ]
        widgets = {"date_of_birth": forms.DateInput(attrs={"type": "date"})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["skills"].required = False
        self.fields["resume"].widget.attrs["class"] = "form-control"


class ApplyForm(BootstrapMixin, forms.Form):
    """Confirmation-only apply form (profile data comes from CandidateProfile)."""

    confirm = forms.BooleanField(
        required=True, label="I confirm my profile is up to date"
    )


__all__ = [
    "ApplyForm",
    "CandidateProfileForm",
    "InviteForm",
    "JobForm",
    "ReviewForm",
    "SkillForm",
    "StageForm",
]
