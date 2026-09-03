"""Forms for the scheduling UI."""

from datetime import time
from functools import lru_cache

from django import forms

from core.models import Membership, User
from scheduling.models import (
    WEEKDAYS,
    InterviewerAvailability,
    known_timezones,
    valid_timezone,
)
from scheduling.services import DEFAULT_DURATION_MINUTES

COMMON_TIMEZONES = [
    "UTC",
    "Asia/Kolkata",
    "Asia/Dubai",
    "Asia/Singapore",
    "Europe/London",
    "Europe/Berlin",
    "America/New_York",
    "America/Chicago",
    "America/Los_Angeles",
    "Australia/Sydney",
]

DURATION_CHOICES = [
    (15, "15 minutes"),
    (30, "30 minutes"),
    (45, "45 minutes"),
    (60, "1 hour"),
    (90, "1 hour 30 minutes"),
    (120, "2 hours"),
]


@lru_cache(maxsize=1)
def timezone_choices():
    """Common zones first, then everything else, so the select stays usable."""
    known = sorted(known_timezones())
    rest = [(name, name) for name in known if name not in COMMON_TIMEZONES]
    return [(name, name) for name in COMMON_TIMEZONES] + rest


class TimezoneField(forms.ChoiceField):
    def __init__(self, **kwargs):
        kwargs.setdefault("choices", timezone_choices)
        kwargs.setdefault("initial", "UTC")
        super().__init__(**kwargs)

    def clean(self, value):
        return valid_timezone(super().clean(value))


class AvailabilityForm(forms.ModelForm):
    """One weekly window for the signed-in interviewer."""

    timezone = TimezoneField(label="Timezone")

    class Meta:
        model = InterviewerAvailability
        fields = ["weekday", "start", "end", "timezone"]
        widgets = {
            "weekday": forms.Select(attrs={"class": "form-select"}),
            "start": forms.TimeInput(attrs={"type": "time", "class": "form-control"}),
            "end": forms.TimeInput(attrs={"type": "time", "class": "form-control"}),
        }

    def __init__(self, *args, company=None, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.company = company
        self.user = user
        self.fields["weekday"].choices = WEEKDAYS
        self.fields["timezone"].widget.attrs["class"] = "form-select"
        self.fields["start"].initial = time(9, 0)
        self.fields["end"].initial = time(17, 0)

    def clean(self):
        data = super().clean()
        start, end = data.get("start"), data.get("end")
        if start and end and end <= start:
            raise forms.ValidationError("The end time must be after the start time.")
        return data

    def save(self, commit=True):
        window = super().save(commit=False)
        window.company = self.company
        window.user = self.user
        if commit:
            window.save()
        return window


class ProposeInterviewForm(forms.Form):
    """Recruiter-side "Schedule interview" panel."""

    interviewers = forms.ModelMultipleChoiceField(
        queryset=User.objects.none(),
        widget=forms.CheckboxSelectMultiple,
        help_text="Only members with declared availability can be booked.",
    )
    duration = forms.TypedChoiceField(
        choices=DURATION_CHOICES, coerce=int, initial=DEFAULT_DURATION_MINUTES
    )
    timezone = TimezoneField(
        label="Present slots in", help_text="Used for the recruiter-side preview."
    )
    location_or_link = forms.CharField(
        max_length=300,
        required=False,
        label="Location or meeting link",
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "https://…"}),
    )
    notes = forms.CharField(
        required=False, widget=forms.Textarea(attrs={"class": "form-control", "rows": 3})
    )

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.company = company
        self.fields["interviewers"].queryset = self.interviewer_queryset(company)
        self.fields["duration"].widget.attrs["class"] = "form-select"
        self.fields["timezone"].widget.attrs["class"] = "form-select"

    @staticmethod
    def interviewer_queryset(company):
        if company is None:
            return User.objects.none()
        return (
            User.objects.filter(
                memberships__company=company,
                memberships__role__in=[
                    Membership.OWNER,
                    Membership.RECRUITER,
                    Membership.INTERVIEWER,
                ],
            )
            .distinct()
            .order_by("email")
        )


class BookingForm(forms.Form):
    """Candidate slot choice on the public booking page."""

    slot = forms.CharField(max_length=64)
    timezone = forms.CharField(max_length=64, required=False)

    def clean_slot(self):
        from scheduling.services import parse_slot_key

        start = parse_slot_key(self.cleaned_data["slot"])
        if start is None:
            raise forms.ValidationError("Pick one of the offered times.")
        return start

    def clean_timezone(self):
        return valid_timezone(self.cleaned_data.get("timezone"))


class CancelBookingForm(forms.Form):
    reason = forms.CharField(
        required=False,
        max_length=300,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 2}),
    )
