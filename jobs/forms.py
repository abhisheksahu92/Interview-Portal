"""Forms for recruiter-facing job configuration."""

from django import forms

from core.permissions import for_company

from .models import Job, PipelineStage, Skill


class SkillForm(forms.ModelForm):
    class Meta:
        model = Skill
        fields = ["name"]

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.company = company

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        qs = for_company(Skill.objects.all(), self.company).filter(name__iexact=name)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError("That skill already exists.")
        return name

    def save(self, commit=True):
        obj = super().save(commit=False)
        if self.company is not None:
            obj.company = self.company
        if commit:
            obj.save()
        return obj


class JobForm(forms.ModelForm):
    class Meta:
        model = Job
        fields = [
            "title",
            "location",
            "description",
            "requirements",
            "employment_type",
            "status",
            "skills",
            "closes_at",
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 5}),
            "requirements": forms.Textarea(attrs={"rows": 5}),
            "closes_at": forms.DateInput(attrs={"type": "date"}),
            "skills": forms.CheckboxSelectMultiple,
        }

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.company = company
        self.fields["skills"].queryset = for_company(Skill.objects.all(), company)

    def save(self, commit=True):
        obj = super().save(commit=False)
        if self.company is not None:
            obj.company = self.company
        if commit:
            obj.save()
            self.save_m2m()
        return obj


class PipelineStageForm(forms.ModelForm):
    class Meta:
        model = PipelineStage
        fields = ["name", "order", "kind", "requires_assessment"]


class ApplyForm(forms.Form):
    """Nothing to collect beyond confirmation; kept for CSRF + future fields."""

    note = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 3}))
