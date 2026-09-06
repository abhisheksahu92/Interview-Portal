from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.urls import reverse
from django.utils.html import format_html

from core.models import Company, Membership, User


class EmailLoginForm(AuthenticationForm):
    username = forms.EmailField(
        label="Email",
        widget=forms.EmailInput(attrs={"autofocus": True, "class": "form-control"}),
    )
    password = forms.CharField(
        label="Password",
        strip=False,
        widget=forms.PasswordInput(attrs={"class": "form-control"}),
    )


class BaseSignupForm(UserCreationForm):
    first_name = forms.CharField(max_length=150, required=False)
    last_name = forms.CharField(max_length=150, required=False)

    class Meta:
        model = User
        fields = ["email", "first_name", "last_name"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-control")


class PolicyConsentMixin(forms.Form):
    """Explicit consent to the published policies, recorded on the user.

    A payment gateway (and the DPDP Act) wants proof that the person agreed,
    not a footer link they may never have seen — so this is a required
    checkbox, unticked by default, and the accepted version is stamped on the
    User in the signup view.
    """

    accept_policies = forms.BooleanField(
        required=True,
        error_messages={
            "required": "You must accept the Terms of Service and Privacy Policy to continue."
        },
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        field = self.fields["accept_policies"]
        # BaseSignupForm defaults every widget to .form-control; a checkbox is
        # the one field where Bootstrap wants a different class.
        field.widget.attrs["class"] = "form-check-input"
        field.label = format_html(
            'I agree to the <a href="{}" target="_blank" rel="noopener">Terms of Service</a> '
            'and the <a href="{}" target="_blank" rel="noopener">Privacy Policy</a>.',
            reverse("web:terms"),
            reverse("web:privacy"),
        )


class CandidateSignupForm(PolicyConsentMixin, BaseSignupForm):
    def save(self, commit=True):
        user = super().save(commit=False)
        user.is_candidate = True
        if commit:
            user.save()
        return user


class CompanySignupForm(PolicyConsentMixin, BaseSignupForm):
    company_name = forms.CharField(max_length=150, label="Company name")

    field_order = ["company_name", "email", "first_name", "last_name"]

    def save(self, commit=True):
        user = super().save(commit=False)
        user.is_candidate = False
        user.save()
        name = self.cleaned_data["company_name"]
        company = Company.objects.create(name=name, slug=Company.unique_slug(name))
        Membership.objects.create(user=user, company=company, role=Membership.OWNER)
        self.company = company
        return user


class InvitedSignupForm(BaseSignupForm):
    """Signup form used when accepting an invitation: the email is fixed."""

    def __init__(self, *args, invitation=None, **kwargs):
        self.invitation = invitation
        if invitation is not None:
            initial = kwargs.setdefault("initial", {})
            initial.setdefault("email", invitation.email)
        super().__init__(*args, **kwargs)
        self.fields["email"].disabled = True
        self.fields["email"].widget.attrs["readonly"] = True

    def clean_email(self):
        if self.invitation is not None:
            return self.invitation.email
        return self.cleaned_data["email"]

    def save(self, commit=True):
        user = super().save(commit=False)
        user.is_candidate = False
        if commit:
            user.save()
        return user
