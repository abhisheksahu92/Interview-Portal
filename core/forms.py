from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm

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


class CandidateSignupForm(BaseSignupForm):
    def save(self, commit=True):
        user = super().save(commit=False)
        user.is_candidate = True
        if commit:
            user.save()
        return user


class CompanySignupForm(BaseSignupForm):
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
