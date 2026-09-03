from django.contrib import messages
from django.contrib.auth import login as auth_login
from django.contrib.auth import logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from core.forms import (
    CandidateSignupForm,
    CompanySignupForm,
    EmailLoginForm,
    InvitedSignupForm,
)
from core.middleware import set_active_company
from core.models import Company, Invitation


class EmailLoginView(LoginView):
    template_name = "core/login.html"
    authentication_form = EmailLoginForm
    redirect_authenticated_user = True


@require_http_methods(["GET", "POST"])
def logout_view(request):
    """Sign out. Only POST mutates; GET renders a confirmation page."""
    if request.method != "POST":
        if not request.user.is_authenticated:
            return redirect("core:login")
        return render(request, "core/logout_confirm.html", {})
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
        set_active_company(request, form.company)
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
        set_active_company(request, company)
        messages.success(request, f"Switched to {company.name}.")
    return redirect(request.POST.get("next") or "/")


@login_required
def account_home(request):
    """Small landing page showing the account's memberships."""
    return render(request, "core/account_home.html", {})


def _invite_error(request, invitation, reason):
    return render(
        request,
        "core/invite_invalid.html",
        {"invitation": invitation, "reason": reason},
        status=400,
    )


@require_http_methods(["GET", "POST"])
def invite_accept(request, token):
    """Accept a company invitation.

    Logged in with the invited email -> join immediately. Anonymous -> offer a
    prefilled signup form (or a link to sign in) that comes back here.
    """
    invitation = get_object_or_404(Invitation, token=token)

    if invitation.is_accepted:
        return _invite_error(
            request, invitation, "This invitation has already been used."
        )
    if invitation.is_expired:
        return _invite_error(
            request,
            invitation,
            "This invitation has expired. Ask the company owner to send a new one.",
        )

    if request.user.is_authenticated:
        if request.user.email.lower() != invitation.email.lower():
            return _invite_error(
                request,
                invitation,
                f"This invitation was sent to {invitation.email}, but you are "
                f"signed in as {request.user.email}. Sign out and try again.",
            )
        if request.method != "POST":
            # Never mutate on GET: show a confirmation with an Accept button.
            return render(
                request,
                "core/invite_confirm.html",
                {"invitation": invitation},
            )
        invitation.accept(request.user)
        set_active_company(request, invitation.company)
        messages.success(request, f"Welcome to {invitation.company.name}!")
        return redirect("/")

    form = InvitedSignupForm(request.POST or None, invitation=invitation)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        auth_login(request, user)
        invitation.accept(user)
        set_active_company(request, invitation.company)
        messages.success(request, f"Welcome to {invitation.company.name}!")
        return redirect("/")

    return render(
        request,
        "core/invite_accept.html",
        {
            "form": form,
            "invitation": invitation,
            "login_url": f"{reverse('core:login')}?next={invitation.accept_url()}",
        },
    )
