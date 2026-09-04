"""Forms for the web UI. All model access goes through jobs/assessments models."""

from django import forms
from django.db import models

from core.models import Invitation, Membership
from jobs.models import CandidateProfile, Job, PipelineStage, Skill, StageReview
from jobs.validators import validate_resume_file


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
            "salary_min",
            "salary_max",
            "salary_currency",
            "salary_period",
            "show_salary",
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 5}),
            "requirements": forms.Textarea(attrs={"rows": 5}),
            "closes_at": forms.DateInput(attrs={"type": "date"}),
            "salary_min": forms.NumberInput(attrs={"step": "1", "min": "0"}),
            "salary_max": forms.NumberInput(attrs={"step": "1", "min": "0"}),
        }
        labels = {
            "salary_min": "Salary from",
            "salary_max": "Salary to",
            "salary_currency": "Currency",
            "salary_period": "Period",
            "show_salary": "Show the salary publicly",
        }

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.company = company
        self.fields["skills"].queryset = Skill.objects.filter(company=company)
        self.fields["skills"].required = False
        # Currency and period always have a sensible default, so the form never
        # forces a recruiter to pick them just to save a job with no salary.
        self.fields["salary_currency"].required = False
        self.fields["salary_period"].required = False

    def clean_salary_currency(self):
        return (self.cleaned_data.get("salary_currency") or "INR").upper()

    def clean_salary_period(self):
        return self.cleaned_data.get("salary_period") or Job.YEAR

    def clean(self):
        """A published range must be a real range: min <= max, and non-empty."""
        cleaned = super().clean()
        low, high = cleaned.get("salary_min"), cleaned.get("salary_max")
        if low is not None and high is not None and low > high:
            self.add_error(
                "salary_max", "The upper salary must be at least the lower salary."
            )
        if cleaned.get("show_salary") and low is None and high is None:
            self.add_error(
                "show_salary",
                "Enter a salary before publishing it on the job page.",
            )
        return cleaned

    def save(self, commit=True):
        job = super().save(commit=False)
        if self.company is not None:
            job.company = self.company
        if commit:
            job.save()
            self.save_m2m()
        return job


class StageForm(BootstrapMixin, forms.ModelForm):
    """Add or edit one pipeline stage. Bound to a job so order stays unique."""

    class Meta:
        model = PipelineStage
        fields = ["name", "order", "kind", "requires_assessment"]

    def __init__(self, *args, job=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.job = job or getattr(self.instance, "job", None)
        if self.job is not None and not self.instance.pk and not self.is_bound:
            existing = self.job.stages.aggregate(m=models.Max("order"))["m"] or 0
            self.fields["order"].initial = existing + 1

    def clean_order(self):
        order = self.cleaned_data["order"]
        if self.job is not None:
            clash = self.job.stages.filter(order=order)
            if self.instance.pk:
                clash = clash.exclude(pk=self.instance.pk)
            if clash.exists():
                raise forms.ValidationError(
                    "Another stage on this job already uses that order number."
                )
        return order

    def save(self, commit=True):
        stage = super().save(commit=False)
        if self.job is not None:
            stage.job = self.job
        if commit:
            stage.save()
        return stage


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
        if company is None and self.instance.pk:
            company = self.instance.company
        self.company = company

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        if self.company is not None:
            clash = Skill.objects.filter(company=self.company, name__iexact=name)
            if self.instance.pk:
                clash = clash.exclude(pk=self.instance.pk)
            if clash.exists():
                raise forms.ValidationError("That skill already exists.")
        return name

    def save(self, commit=True):
        skill = super().save(commit=False)
        skill.company = self.company
        if commit:
            skill.save()
        return skill


class InviteForm(BootstrapMixin, forms.Form):
    """Create a pending core.Invitation for an email address."""

    email = forms.EmailField(help_text="They will get a link that expires in 7 days.")
    role = forms.ChoiceField(
        choices=Membership.ROLE_CHOICES,
        initial=Membership.RECRUITER,
        help_text=(
            "Owner: full access including billing and members. "
            "Recruiter: jobs, pipelines and candidates. "
            "Interviewer: review queue only."
        ),
    )

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
    """Candidate self-service profile.

    Skills are shown de-duplicated by name (they are per-company rows, so the
    same name exists once per tenant) and résumés are validated for extension,
    size and magic bytes by ``jobs.validators.validate_resume_file``.
    """

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
        widgets = {
            "date_of_birth": forms.DateInput(attrs={"type": "date"}),
            "skills": forms.CheckboxSelectMultiple,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["skills"].required = False
        self.fields["skills"].queryset = Skill.objects.distinct_by_name()
        # BootstrapMixin cannot tell checkbox groups apart from text inputs.
        self.fields["skills"].widget.attrs["class"] = "form-check-input"
        self.fields["resume"].required = False
        self.fields["resume"].help_text = (
            "PDF, DOC, DOCX or TXT, up to 5 MB."
        )
        self.fields["resume"].widget.attrs.update(
            {
                "class": "form-control",
                "accept": ".pdf,.doc,.docx,.txt,application/pdf,application/msword,"
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document,"
                "text/plain",
            }
        )

    def clean_resume(self):
        """Run the shared validator eagerly so the error lands on this field."""
        resume = self.cleaned_data.get("resume")
        if resume and hasattr(resume, "file"):  # a freshly uploaded file
            validate_resume_file(resume)
        return resume


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
