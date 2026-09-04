from django.contrib import messages
from django.contrib.auth import login as auth_login
from django.contrib.auth import logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.http import Http404, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.html import escape
from django.views.decorators.http import require_http_methods

from core.forms import (
    CandidateSignupForm,
    CompanySignupForm,
    EmailLoginForm,
    InvitedSignupForm,
)
from core.middleware import set_active_company
from core.models import Company, Invitation, Membership
from core.tokens import TokenState, resolve_token, token_invalid_response


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


def _invite_error(request, invitation, reason, state=TokenState.REVOKED):
    """Render the shared token-invalid page inside the app shell.

    Invitations answer **400** rather than the 404/410 that
    :class:`core.tokens.TokenState` would pick — that is the contract the
    invite links have always had (see ARCHITECTURE.md, "Tokens").
    """
    return token_invalid_response(
        request,
        state,
        status=400,
        context={
            "invitation": invitation,
            "reason": reason,
            "page_title": "Invitation unavailable",
            "contact_hint": "Ask the company owner to send you a new invitation.",
            "show_auth_links": True,
        },
    )


@require_http_methods(["GET", "POST"])
def invite_accept(request, token):
    """Accept a company invitation.

    Logged in with the invited email -> join immediately. Anonymous -> offer a
    prefilled signup form (or a link to sign in) that comes back here.
    """
    resolution = resolve_token(Invitation, token, select_related=("company",))
    if resolution.state is TokenState.UNKNOWN:
        raise Http404("No such invitation.")
    invitation = resolution.obj

    if invitation.is_accepted:
        return _invite_error(
            request, invitation, "This invitation has already been used."
        )
    if resolution.state is TokenState.EXPIRED:
        return _invite_error(
            request,
            invitation,
            "This invitation has expired. Ask the company owner to send a new one.",
            state=TokenState.EXPIRED,
        )
    if resolution.state is TokenState.REVOKED:
        return _invite_error(request, invitation, "This invitation was revoked.")

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


# --------------------------------------------------------------------------
# Error handlers
# --------------------------------------------------------------------------
def permission_denied(request, exception=None, template_name="403.html"):
    """handler403 that tells a plan problem apart from a role problem.

    ``billing.entitlements.FeatureNotAvailable`` means the workspace's plan is
    missing a feature, which an owner can fix by upgrading; anything else is a
    role problem, which only an owner can grant.
    """
    from billing.entitlements import FeatureNotAvailable

    company = getattr(request, "company", None)
    feature = None
    if isinstance(exception, FeatureNotAvailable):
        feature = getattr(exception, "feature", "") or ""
    user = getattr(request, "user", None)
    is_owner = False
    if feature and user is not None and getattr(user, "is_authenticated", False):
        is_owner = user.role_in(company) == Membership.OWNER
    context = {
        "feature": feature,
        "feature_label": feature.replace("_", " ").title() if feature else "",
        "is_owner": is_owner,
    }
    return render(request, template_name, context, status=403)


# --------------------------------------------------------------------------
# Site root: robots.txt + sitemap.xml
# --------------------------------------------------------------------------
def _site_base(request):
    """Absolute site root, preferring the live request over ``SITE_URL``."""
    return request.build_absolute_uri("/").rstrip("/")


def robots_txt(request):
    """Allow every crawler and point at the sitemap."""
    body = "\n".join(
        [
            "User-agent: *",
            "Allow: /",
            f"Sitemap: {_site_base(request)}{reverse('sitemap_xml')}",
            "",
        ]
    )
    return HttpResponse(body, content_type="text/plain")


def sitemap_xml(request):
    """Root sitemap: the landing page plus every published careers site.

    Each careers site keeps its own per-site sitemap (jobs included); this
    document points crawlers at all of them from one place.
    """
    base = _site_base(request)
    locs = [base + reverse("web:home")]
    try:
        from careers.models import CareersSite

        for site in CareersSite.objects.filter(published=True).order_by("slug"):
            locs.append(base + reverse("careers:site", args=[site.slug]))
            locs.append(base + reverse("careers:sitemap", args=[site.slug]))
    except Exception:  # pragma: no cover - careers is optional
        pass
    entries = "".join(f"<url><loc>{escape(loc)}</loc></url>" for loc in locs)
    body = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        f"{entries}</urlset>"
    )
    return HttpResponse(body, content_type="application/xml")
