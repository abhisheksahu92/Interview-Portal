"""Forms for the video app's recruiter screens."""

from django import forms

from jobs.models import PipelineStage, StageReview
from video.models import VideoQuestion, VideoScreen


class VideoQuestionForm(forms.ModelForm):
    """Create/edit a reusable question in the company library."""

    class Meta:
        model = VideoQuestion
        fields = ["text", "think_seconds", "answer_seconds", "order"]
        widgets = {
            "text": forms.Textarea(attrs={"rows": 3, "class": "form-control"}),
            "think_seconds": forms.NumberInput(attrs={"class": "form-control", "min": 5}),
            "answer_seconds": forms.NumberInput(attrs={"class": "form-control", "min": 15}),
            "order": forms.NumberInput(attrs={"class": "form-control", "min": 0}),
        }

    def clean_think_seconds(self):
        value = self.cleaned_data["think_seconds"]
        if value > 600:
            raise forms.ValidationError("Keep think time under 10 minutes.")
        return value

    def clean_answer_seconds(self):
        value = self.cleaned_data["answer_seconds"]
        if value < 15:
            raise forms.ValidationError("Give candidates at least 15 seconds to answer.")
        if value > 900:
            raise forms.ValidationError("Keep answers under 15 minutes.")
        return value


class VideoScreenForm(forms.ModelForm):
    """Build a screen for one job: pick the stage and its questions."""

    questions = forms.ModelMultipleChoiceField(
        queryset=VideoQuestion.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        help_text="Questions are asked in their library order.",
    )

    class Meta:
        model = VideoScreen
        fields = ["title", "stage", "deadline_days", "is_active"]
        widgets = {
            "title": forms.TextInput(attrs={"class": "form-control"}),
            "stage": forms.Select(attrs={"class": "form-select"}),
            "deadline_days": forms.NumberInput(attrs={"class": "form-control", "min": 1}),
        }

    def __init__(self, *args, job=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.job = job or getattr(self.instance, "job", None)
        company = self.job.company if self.job else None
        self.fields["questions"].queryset = VideoQuestion.objects.filter(company=company)
        self.fields["stage"].queryset = PipelineStage.objects.filter(job=self.job)
        self.fields["stage"].required = False
        self.fields["stage"].empty_label = "Any stage (job-wide)"
        if self.instance.pk:
            self.initial["questions"] = list(
                self.instance.questions.values_list("pk", flat=True)
            )

    def save(self, commit=True):
        screen = super().save(commit=False)
        if self.job is not None:
            screen.job = self.job
        screen.save()
        self._sync_questions(screen)
        return screen

    def _sync_questions(self, screen):
        from video.models import VideoScreenQuestion

        chosen = list(self.cleaned_data.get("questions") or [])
        VideoScreenQuestion.objects.filter(screen=screen).exclude(
            question__in=chosen
        ).delete()
        for index, question in enumerate(chosen):
            VideoScreenQuestion.objects.update_or_create(
                screen=screen, question=question, defaults={"order": index}
            )


class QuickReviewForm(forms.Form):
    """Recruiter's PASS/FAIL/HOLD decision straight from the playback page."""

    decision = forms.ChoiceField(
        choices=StageReview.DECISION_CHOICES,
        widget=forms.RadioSelect,
    )
    rating = forms.TypedChoiceField(
        choices=[("", "No rating")] + [(i, f"{i}") for i in range(1, 6)],
        coerce=int,
        empty_value=None,
        required=False,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    feedback = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 3, "class": "form-control"}),
    )
