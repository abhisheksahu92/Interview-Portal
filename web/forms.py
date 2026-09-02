"""Forms for the web UI. All model access goes through jobs/assessments models."""

from django import forms

from core.models import Membership, User
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
    email = forms.EmailField()
    role = forms.ChoiceField(choices=Membership.ROLE_CHOICES)

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.company = company
        self.created_user = False

    def clean_email(self):
        return self.cleaned_data["email"].strip().lower()

    def save(self):
        """Create the Membership, creating an inactive placeholder user if needed."""
        email = self.cleaned_data["email"]
        user = User.objects.filter(email__iexact=email).first()
        if user is None:
            user = User.objects.create_user(email=email, password=None)
            user.is_active = False
            user.set_unusable_password()
            user.save(update_fields=["is_active", "password"])
            self.created_user = True
        membership, _ = Membership.objects.get_or_create(
            user=user,
            company=self.company,
            defaults={"role": self.cleaned_data["role"]},
        )
        if membership.role != self.cleaned_data["role"]:
            membership.role = self.cleaned_data["role"]
            membership.save(update_fields=["role"])
        return membership


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
