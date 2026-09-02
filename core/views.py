from django.contrib import messages
from django.contrib.auth import login as auth_login
from django.contrib.auth import logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from core.forms import CandidateSignupForm, CompanySignupForm, EmailLoginForm
from core.middleware import TenantMiddleware
from core.models import Company


class EmailLoginView(LoginView):
    template_name = "core/login.html"
    authentication_form = EmailLoginForm
    redirect_authenticated_user = True


@require_http_methods(["GET", "POST"])
def logout_view(request):
    auth_logout(request)
    messages.info(request, "You have been signed out.")
    return redirect("core:login")


def candidate_signup(request):
    form = CandidateSignupForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        auth_login(request, user)
        messages.success(request, "Welcome! Your candidate account is ready.")
        return redirect("/")
    return render(
        request,
        "core/signup_candidate.html",
        {"form": form},
    )


def company_signup(request):
    form = CompanySignupForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        auth_login(request, user)
        request.session[TenantMiddleware.session_key] = form.company.id
        messages.success(request, f"Company '{form.company.name}' created.")
        return redirect("/")
    return render(
        request,
        "core/signup_company.html",
        {"form": form},
    )


@login_required
@require_http_methods(["POST"])
def switch_company(request):
    company_id = request.POST.get("company_id")
    company = Company.objects.filter(
        id=company_id, memberships__user=request.user
    ).first()
    if company is None:
        messages.error(request, "You are not a member of that company.")
    else:
        request.session[TenantMiddleware.session_key] = company.id
        messages.success(request, f"Switched to {company.name}.")
    return redirect(request.POST.get("next") or "/")


@login_required
def account_home(request):
    """Small landing page showing the account's memberships."""
    return render(request, "core/account_home.html", {})
