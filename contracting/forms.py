"""Forms for the contracting workspace.

Every form that touches another tenant's rows takes ``company`` and narrows its
querysets to it, so a hand-crafted POST cannot attach a contractor to someone
else's client.
"""

from datetime import timedelta

from django import forms
from django.utils import timezone

from clients.models import Client
from contracting.models import (
    ClientBillingProfile,
    Contractor,
    Engagement,
    OnboardingDocument,
    Timesheet,
)
from jobs.models import Job


class ContractorForm(forms.ModelForm):
    """Contractor profile plus the four bank fields kept in the encrypted blob."""

    bank_holder = forms.CharField(label="Account holder", max_length=120, required=False)
    bank_account_number = forms.CharField(label="Account number", max_length=30, required=False)
    bank_ifsc = forms.CharField(label="IFSC", max_length=15, required=False)
    bank_name = forms.CharField(label="Bank", max_length=120, required=False)

    class Meta:
        model = Contractor
        fields = [
            "name",
            "email",
            "phone",
            "pan",
            "uan",
            "employee_id",
            "status",
            "notes",
        ]
        widgets = {"notes": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.company = company
        bank = (self.instance.bank if self.instance and self.instance.pk else {}) or {}
        for field, key in self._bank_map().items():
            self.fields[field].initial = bank.get(key, "")
        for field in self.fields.values():
            css = "form-select" if isinstance(field.widget, forms.Select) else "form-control"
            field.widget.attrs.setdefault("class", css)

    @staticmethod
    def _bank_map():
        return {
            "bank_holder": "holder",
            "bank_account_number": "account_number",
            "bank_ifsc": "ifsc",
            "bank_name": "bank_name",
        }

    def clean_pan(self):
        return (self.cleaned_data.get("pan") or "").upper().strip()

    def save(self, commit=True):
        contractor = super().save(commit=False)
        if self.company is not None:
            contractor.company = self.company
        bank = dict(contractor.bank or {})
        for field, key in self._bank_map().items():
            bank[key] = (self.cleaned_data.get(field) or "").strip()
        contractor.bank = {k: v for k, v in bank.items() if v}
        if commit:
            contractor.save()
        return contractor


class EngagementForm(forms.ModelForm):
    class Meta:
        model = Engagement
        fields = [
            "client",
            "job",
            "role_title",
            "start",
            "end",
            "bill_rate_inr",
            "pay_rate_inr",
            "rate_unit",
            "tds_percent",
            "po_number",
            "status",
        ]
        widgets = {
            "start": forms.DateInput(attrs={"type": "date"}),
            "end": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, company=None, contractor=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.company = company
        self.contractor = contractor
        self.fields["client"].queryset = Client.objects.for_company(company)
        self.fields["job"].queryset = Job.objects.filter(company=company) if company else Job.objects.none()
        self.fields["job"].required = False
        self.fields["end"].required = False
        self.fields["start"].initial = timezone.localdate()
        for field in self.fields.values():
            css = "form-select" if isinstance(field.widget, forms.Select) else "form-control"
            field.widget.attrs.setdefault("class", css)

    def clean(self):
        cleaned = super().clean()
        start, end = cleaned.get("start"), cleaned.get("end")
        if start and end and end < start:
            self.add_error("end", "The end date cannot be before the start date.")
        bill, pay = cleaned.get("bill_rate_inr"), cleaned.get("pay_rate_inr")
        if bill is not None and pay is not None and pay > bill:
            self.add_error("pay_rate_inr", "The pay rate cannot exceed the bill rate.")
        return cleaned

    def save(self, commit=True):
        engagement = super().save(commit=False)
        if self.contractor is not None:
            engagement.contractor = self.contractor
        if commit:
            engagement.save()
        return engagement


class OnboardingDocumentForm(forms.ModelForm):
    class Meta:
        model = OnboardingDocument
        fields = ["kind", "file", "note"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["kind"].widget.attrs.setdefault("class", "form-select")
        self.fields["file"].widget.attrs.setdefault("class", "form-control")
        self.fields["note"].widget.attrs.setdefault("class", "form-control")
        self.fields["note"].required = False


class ClientBillingProfileForm(forms.ModelForm):
    class Meta:
        model = ClientBillingProfile
        fields = [
            "gstin",
            "state_code",
            "billing_email",
            "billing_address",
            "payment_terms_days",
        ]
        widgets = {"billing_address": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.required = False
            field.widget.attrs.setdefault("class", "form-control")
        self.fields["payment_terms_days"].required = True
        # Django would title-case this to "Gstin".
        self.fields["gstin"].label = "GSTIN"

    def clean_state_code(self):
        code = (self.cleaned_data.get("state_code") or "").strip()
        if code and (not code.isdigit() or len(code) != 2):
            raise forms.ValidationError("Use the two-digit GST state code, e.g. 27.")
        return code

    def clean_gstin(self):
        return (self.cleaned_data.get("gstin") or "").upper().strip()


class PeriodForm(forms.Form):
    """A month picker shared by the invoice run and the payroll run."""

    # ``type="month"`` only accepts a "YYYY-MM" value; rendering the default
    # "YYYY-MM-DD" leaves the picker empty and the form unsubmittable.
    month = forms.DateField(
        widget=forms.DateInput(
            attrs={"type": "month", "class": "form-control"}, format="%Y-%m"
        ),
        input_formats=["%Y-%m-%d", "%Y-%m"],
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["month"].initial = timezone.localdate().replace(day=1)

    def clean_month(self):
        return self.cleaned_data["month"].replace(day=1)


class TimesheetDecisionForm(forms.Form):
    """The approve/reject note captured in the client portal and the queue."""

    note = forms.CharField(
        required=False,
        max_length=1000,
        widget=forms.Textarea(attrs={"rows": 2, "class": "form-control form-control-sm"}),
    )


def parse_grid(post_data, timesheet):
    """Read a submitted weekly grid into ``[{date, hours, note}]``.

    Fields are named ``hours-<iso date>`` and ``note-<iso date>``; anything
    outside the timesheet's own period is ignored, so a tampered POST cannot log
    hours into a period nobody approved.
    """
    entries = []
    day = timesheet.period_start
    while day <= timesheet.period_end:
        key = day.isoformat()
        raw = (post_data.get(f"hours-{key}") or "").strip()
        note = (post_data.get(f"note-{key}") or "").strip()
        hours = 0
        if raw:
            try:
                hours = float(raw)
            except ValueError:
                hours = 0
        if hours or note:
            entries.append({"date": key, "hours": max(hours, 0), "note": note})
        day += timedelta(days=1)
    return entries


class TimesheetGridForm(forms.Form):
    """Validation for the grid as a whole (per-day caps live here)."""

    MAX_HOURS_PER_DAY = 24

    def __init__(self, *args, timesheet=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.timesheet = timesheet
        self.entries = []

    def clean(self):
        cleaned = super().clean()
        entries = parse_grid(self.data, self.timesheet)
        for entry in entries:
            if entry["hours"] > self.MAX_HOURS_PER_DAY:
                raise forms.ValidationError(
                    f"{entry['date']}: a day cannot hold more than "
                    f"{self.MAX_HOURS_PER_DAY} hours."
                )
        self.entries = entries
        return cleaned


TIMESHEET_STATUS_CHOICES = [("", "All statuses")] + Timesheet.STATUS_CHOICES
