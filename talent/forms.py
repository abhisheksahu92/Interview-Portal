"""Forms for talent search, import and profile editing."""

from django import forms

from core.permissions import for_company
from jobs.models import Skill
from talent.models import TalentProfile
from talent.services import MAX_FILES


class TalentSearchForm(forms.Form):
    """The search bar + filter panel on the talent index."""

    ORDERING_CHOICES = [
        ("recent", "Recently updated"),
        ("name", "Name (A-Z)"),
        ("experience", "Most experience"),
        ("created", "Newest first"),
    ]

    q = forms.CharField(
        required=False,
        label="Search",
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Name, email, headline, resume text or tag",
                "autocomplete": "off",
            }
        ),
    )
    skills = forms.ModelMultipleChoiceField(
        queryset=Skill.objects.none(),
        required=False,
        widget=forms.SelectMultiple(attrs={"class": "form-select", "size": 6}),
    )
    match_all = forms.BooleanField(
        required=False,
        label="Must have every selected skill",
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )
    min_experience = forms.DecimalField(
        required=False,
        min_value=0,
        max_value=60,
        label="Min years",
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.5"}),
    )
    max_experience = forms.DecimalField(
        required=False,
        min_value=0,
        max_value=60,
        label="Max years",
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.5"}),
    )
    tags = forms.CharField(
        required=False,
        label="Tags",
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "python, senior"}),
    )
    source = forms.ChoiceField(
        required=False,
        choices=[("", "Any source"), *TalentProfile.SOURCE_CHOICES],
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    ordering = forms.ChoiceField(
        required=False,
        choices=ORDERING_CHOICES,
        initial="recent",
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["skills"].queryset = for_company(Skill.objects.all(), company).order_by("name")

    def clean_min_experience(self):
        return self.cleaned_data.get("min_experience")

    def clean(self):
        data = super().clean()
        low, high = data.get("min_experience"), data.get("max_experience")
        if low is not None and high is not None and low > high:
            self.add_error("max_experience", "Max years must be at least the min.")
        return data

    def criteria(self):
        """Kwargs for :func:`talent.services.search_profiles`."""
        data = self.cleaned_data if self.is_valid() else {}
        return {
            "query": data.get("q") or "",
            "skills": [s.pk for s in data.get("skills") or []],
            "match_all": bool(data.get("match_all")),
            "min_experience": data.get("min_experience"),
            "max_experience": data.get("max_experience"),
            "tags": data.get("tags") or "",
            "source": data.get("source") or "",
            "ordering": data.get("ordering") or "recent",
        }


class MultiFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class ImportForm(forms.Form):
    """Upload a zip, a CSV, or up to ``MAX_FILES`` individual resumes."""

    files = forms.FileField(
        widget=MultiFileInput(
            attrs={"class": "form-control", "multiple": True, "accept": ".zip,.csv,.pdf,.docx,.doc,.txt"}
        ),
        label="Resumes, ZIP archive or CSV",
        help_text=(
            f"PDF, DOCX or TXT resumes (up to {MAX_FILES}), one ZIP archive, "
            "or a CSV with name,email,phone,skills,experience columns. 25 MB total."
        ),
    )

    def uploads(self, request):
        return request.FILES.getlist("files")


class TalentProfileForm(forms.ModelForm):
    """Manual create / edit of a pool profile."""

    class Meta:
        model = TalentProfile
        fields = (
            "name",
            "email",
            "phone",
            "headline",
            "experience_years",
            "current_company",
            "location",
            "resume",
            "skills",
            "notes",
        )
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "email": forms.EmailInput(attrs={"class": "form-control"}),
            "phone": forms.TextInput(attrs={"class": "form-control"}),
            "headline": forms.TextInput(attrs={"class": "form-control"}),
            "experience_years": forms.NumberInput(attrs={"class": "form-control", "step": "0.5"}),
            "current_company": forms.TextInput(attrs={"class": "form-control"}),
            "location": forms.TextInput(attrs={"class": "form-control"}),
            "resume": forms.ClearableFileInput(attrs={"class": "form-control"}),
            "skills": forms.SelectMultiple(attrs={"class": "form-select", "size": 6}),
            "notes": forms.Textarea(attrs={"class": "form-control", "rows": 4}),
        }

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.company = company
        self.fields["skills"].queryset = for_company(Skill.objects.all(), company).order_by("name")
        self.fields["skills"].required = False

    def clean_email(self):
        email = (self.cleaned_data.get("email") or "").strip().lower()
        clash = TalentProfile.objects.filter(company=self.company, email=email)
        if self.instance.pk:
            clash = clash.exclude(pk=self.instance.pk)
        if clash.exists():
            raise forms.ValidationError("This email is already in your talent pool.")
        return email


class NoteForm(forms.ModelForm):
    """Recruiter notes on a profile."""

    class Meta:
        model = TalentProfile
        fields = ("notes",)
        widgets = {"notes": forms.Textarea(attrs={"class": "form-control", "rows": 5})}
