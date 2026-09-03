"""Forms for the clients app.

``JobClientForm`` is published here for the web/ integration agent so the job
create/edit screens can set ``Job.client`` without web/ importing clients models
directly (see the docstring on that class).
"""

from django import forms

from clients.models import Client, ClientAccess, Submission

_CTRL = {"class": "form-control"}
_SELECT = {"class": "form-select"}


class ClientForm(forms.ModelForm):
    class Meta:
        model = Client
        fields = ["name", "contact_name", "contact_email", "logo", "notes"]
        widgets = {
            "name": forms.TextInput(attrs=_CTRL),
            "contact_name": forms.TextInput(attrs=_CTRL),
            "contact_email": forms.EmailInput(attrs=_CTRL),
            "logo": forms.ClearableFileInput(attrs={"class": "form-control"}),
            "notes": forms.Textarea(attrs={**_CTRL, "rows": 3}),
        }

    def __init__(self, *args, company=None, **kwargs):
        self.company = company
        super().__init__(*args, **kwargs)

    def clean_name(self):
        name = (self.cleaned_data["name"] or "").strip()
        company = self.company
        if company is None and self.instance.company_id:
            company = self.instance.company
        if company is not None:
            clash = Client.objects.filter(company=company, name__iexact=name)
            if self.instance.pk:
                clash = clash.exclude(pk=self.instance.pk)
            if clash.exists():
                raise forms.ValidationError("A client with this name already exists.")
        return name

    def save(self, commit=True):
        obj = super().save(commit=False)
        if self.company is not None:
            obj.company = self.company
        if commit:
            obj.save()
        return obj


class ClientAccessForm(forms.ModelForm):
    """Generate a portal link for a client contact."""

    valid_days = forms.IntegerField(
        min_value=1,
        max_value=365,
        initial=ClientAccess.DEFAULT_VALID_DAYS,
        widget=forms.NumberInput(attrs=_CTRL),
        help_text="Days before the link expires.",
    )

    class Meta:
        model = ClientAccess
        fields = ["email"]
        widgets = {"email": forms.EmailInput(attrs=_CTRL)}


class SubmitToClientForm(forms.Form):
    """Recruiter action: put one application in front of a client."""

    client = forms.ModelChoiceField(
        queryset=Client.objects.none(), widget=forms.Select(attrs=_SELECT)
    )
    note = forms.CharField(
        required=False, widget=forms.Textarea(attrs={**_CTRL, "rows": 3})
    )
    notify_client = forms.BooleanField(
        required=False, initial=True, widget=forms.CheckboxInput(attrs={"class": "form-check-input"})
    )

    def __init__(self, *args, company=None, application=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.company = company
        self.application = application
        self.fields["client"].queryset = Client.objects.for_company(company)
        if application is not None and application.job.client_id:
            self.fields["client"].initial = application.job.client_id

    def clean_client(self):
        client = self.cleaned_data["client"]
        if self.company is not None and client.company_id != self.company.pk:
            raise forms.ValidationError("That client belongs to another company.")
        if self.application is not None and Submission.objects.filter(
            application=self.application, client=client
        ).exists():
            raise forms.ValidationError("This candidate has already been submitted to that client.")
        return client


class ClientFeedbackForm(forms.Form):
    """The portal-side decision form (no login, token-scoped)."""

    DECISION_CHOICES = [
        (Submission.SHORTLISTED, "Shortlist"),
        (Submission.REJECTED, "Reject"),
        (Submission.INTERVIEW_REQUESTED, "Request interview"),
    ]

    decision = forms.ChoiceField(choices=DECISION_CHOICES, widget=forms.RadioSelect)
    comment = forms.CharField(
        required=False, widget=forms.Textarea(attrs={**_CTRL, "rows": 3})
    )
    rating = forms.TypedChoiceField(
        required=False,
        coerce=int,
        empty_value=None,
        choices=[("", "No rating")] + [(str(i), f"{i} / 5") for i in range(1, 6)],
        widget=forms.Select(attrs=_SELECT),
    )


class JobClientForm(forms.Form):
    """Set (or clear) the end client on a job.

    Integration note for the web/ agent — you can either POST this form to
    ``clients:job_client`` (``{% url 'clients:job_client' job.pk %}``) or embed the
    field in your own job form::

        from clients.forms import JobClientForm
        form = JobClientForm(company=request.company, job=job)

    ``form.apply(job)`` assigns ``job.client`` and saves the single field.
    """

    client = forms.ModelChoiceField(
        queryset=Client.objects.none(),
        required=False,
        empty_label="— No client (direct hire) —",
        widget=forms.Select(attrs=_SELECT),
        label="End client",
    )

    def __init__(self, *args, company=None, job=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.company = company
        self.job = job
        self.fields["client"].queryset = Client.objects.for_company(company)
        if job is not None and not self.is_bound:
            self.fields["client"].initial = job.client_id

    def clean_client(self):
        client = self.cleaned_data.get("client")
        if client is not None and self.company is not None and client.company_id != self.company.pk:
            raise forms.ValidationError("That client belongs to another company.")
        return client

    def apply(self, job=None):
        job = job or self.job
        job.client = self.cleaned_data.get("client")
        job.save(update_fields=["client"])
        return job
