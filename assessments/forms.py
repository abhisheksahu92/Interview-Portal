"""Forms for the question bank, assessment builder and AI generation."""

from django import forms

from assessments.models import Assessment, Question


class QuestionForm(forms.ModelForm):
    """Question bank entry. ``options`` is edited as one choice per line."""

    options_text = forms.CharField(
        label="Options (one per line)",
        widget=forms.Textarea(attrs={"rows": 4}),
        required=False,
    )

    class Meta:
        model = Question
        fields = ["skill", "kind", "text", "correct_option", "difficulty"]
        widgets = {"text": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.company = company or getattr(self.instance, "company_id", None) and self.instance.company
        if self.company is not None:
            self.fields["skill"].queryset = self.company.skills.all()
        self.fields["skill"].required = False
        if self.instance.pk and not self.data:
            self.fields["options_text"].initial = "\n".join(self.instance.options or [])
        for field in self.fields.values():
            css = "form-select" if isinstance(field.widget, forms.Select) else "form-control"
            field.widget.attrs.setdefault("class", css)

    def clean(self):
        cleaned = super().clean()
        options = [
            line.strip()
            for line in (cleaned.get("options_text") or "").splitlines()
            if line.strip()
        ]
        cleaned["options"] = options
        if cleaned.get("kind") == Question.MCQ:
            if len(options) < 2:
                self.add_error("options_text", "Give at least two options for an MCQ.")
            correct = cleaned.get("correct_option")
            if correct is None:
                self.add_error("correct_option", "Pick the 0-based index of the answer.")
            elif options and correct >= len(options):
                self.add_error("correct_option", "That option index does not exist.")
        else:
            cleaned["options"] = []
            cleaned["correct_option"] = None
        return cleaned

    def save(self, commit=True):
        question = super().save(commit=False)
        question.options = self.cleaned_data.get("options", [])
        if question.kind != Question.MCQ:
            question.correct_option = None
        if self.company is not None:
            question.company = self.company
        if commit:
            question.save()
        return question


class AssessmentForm(forms.ModelForm):
    class Meta:
        model = Assessment
        fields = [
            "title",
            "stage",
            "questions",
            "time_limit_minutes",
            "pass_mark_percent",
            "is_active",
        ]
        widgets = {"questions": forms.CheckboxSelectMultiple()}

    def __init__(self, *args, job=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.job = job or getattr(self.instance, "job", None)
        if self.job is not None:
            self.fields["stage"].queryset = self.job.stages.all()
            self.fields["questions"].queryset = Question.objects.filter(
                company=self.job.company
            )
        self.fields["stage"].required = False
        for name, field in self.fields.items():
            if name == "questions":
                continue
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.setdefault("class", "form-check-input")
            elif isinstance(field.widget, forms.Select):
                field.widget.attrs.setdefault("class", "form-select")
            else:
                field.widget.attrs.setdefault("class", "form-control")

    def save(self, commit=True):
        assessment = super().save(commit=False)
        if self.job is not None:
            assessment.job = self.job
        if commit:
            assessment.save()
            self.save_m2m()
        return assessment


class GenerateQuestionsForm(forms.Form):
    """Inputs for the "generate with AI" action."""

    job = forms.ModelChoiceField(queryset=None)
    skill = forms.ModelChoiceField(queryset=None, required=False)
    n = forms.IntegerField(min_value=1, max_value=20, initial=5, label="How many")
    kind = forms.ChoiceField(choices=Question.KIND_CHOICES, initial=Question.MCQ)

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        from jobs.models import Job

        self.company = company
        jobs = Job.objects.filter(company=company) if company else Job.objects.none()
        self.fields["job"].queryset = jobs
        self.fields["skill"].queryset = company.skills.all() if company else None
        for field in self.fields.values():
            css = "form-select" if isinstance(field.widget, forms.Select) else "form-control"
            field.widget.attrs.setdefault("class", css)


class ManualScoreForm(forms.Form):
    """Recruiter-entered score for one free-text answer of an attempt."""

    question = forms.IntegerField(widget=forms.HiddenInput)
    score = forms.IntegerField(
        min_value=0, max_value=100, label="Score (0-100)"
    )

    def __init__(self, *args, attempt=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.attempt = attempt
        self.fields["score"].widget.attrs.setdefault("class", "form-control")
        self.fields["score"].widget.attrs.setdefault("style", "max-width:7rem")

    def clean_question(self):
        pk = self.cleaned_data["question"]
        if self.attempt is None:
            raise forms.ValidationError("No attempt selected.")
        question = self.attempt.assessment.questions.filter(pk=pk).first()
        if question is None:
            raise forms.ValidationError("That question is not part of this assessment.")
        if question.is_mcq:
            raise forms.ValidationError("Only free-text answers are scored manually.")
        return question
