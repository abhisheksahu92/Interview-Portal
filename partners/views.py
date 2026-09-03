"""Branding / partner-programme screens and the reseller dashboard."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from billing.entitlements import has_feature
from core.permissions import role_required
from partners.forms import ResellerForm, WhiteLabelForm
from partners.licensing import verify_license
from partners.models import CommissionLedger, License, Reseller, WhiteLabel
from partners.referral import set_ref_cookie
from partners.services import referral_for, reseller_totals


@login_required
@role_required("OWNER")
def settings_view(request):
    """Settings ▸ Branding & Partners (tabs: branding, partners)."""
    company = request.company
    tab = request.GET.get("tab") or "branding"
    if tab not in {"branding", "partners"}:
        tab = "branding"
    can_white_label = has_feature(company, "white_label")
    white_label = WhiteLabel.objects.filter(company=company).first()
    form = None
    if can_white_label:
        instance = white_label or WhiteLabel(company=company)
        if request.method == "POST" and request.POST.get("form") == "branding":
            form = WhiteLabelForm(request.POST, request.FILES, instance=instance)
            if form.is_valid():
                obj = form.save(commit=False)
                obj.company = company
                obj.save()
                messages.success(request, "Branding updated.")
                return redirect(f"{reverse('partners:settings')}?tab=branding")
        else:
            form = WhiteLabelForm(instance=instance)

    reseller_form = None
    resellers = Reseller.objects.none()
    if request.user.is_staff:
        resellers = Reseller.objects.all()
        if request.method == "POST" and request.POST.get("form") == "reseller":
            reseller_form = ResellerForm(request.POST)
            if reseller_form.is_valid():
                reseller_form.save()
                messages.success(request, "Reseller saved.")
                return redirect(f"{reverse('partners:settings')}?tab=partners")
        else:
            reseller_form = ResellerForm()

    return render(
        request,
        "partners/settings.html",
        {
            "tab": tab,
            "can_white_label": can_white_label,
            "form": form,
            "white_label": white_label,
            "reseller_form": reseller_form,
            "resellers": resellers,
            "referral": referral_for(company),
            "licenses": License.objects.filter(company=company),
        },
    )


def referral_link(request, code):
    """Set the 30-day ``ip_ref`` cookie then send the visitor to company signup."""
    code = (code or "").strip().lower()
    if not Reseller.objects.filter(code=code, active=True).exists():
        raise Http404("Unknown referral code.")
    response = HttpResponseRedirect(f"{reverse('core:company_signup')}?ref={code}")
    request.session["ip_ref"] = code
    return set_ref_cookie(response, code)


def reseller_dashboard(request, code):
    """Token-authenticated reseller view of referrals, commissions and payouts."""
    reseller = get_object_or_404(Reseller, code=(code or "").strip().lower())
    token = request.GET.get("t") or ""
    if not token or token != reseller.token:
        raise PermissionDenied("A valid dashboard token is required.")
    referrals = reseller.referrals.select_related("company")
    commissions = CommissionLedger.objects.filter(reseller=reseller).select_related("company")
    return render(
        request,
        "partners/reseller_dashboard.html",
        {
            "reseller": reseller,
            "referrals": referrals,
            "commissions": commissions,
            "totals": reseller_totals(reseller),
            "referral_url": request.build_absolute_uri(
                reverse("partners:referral_link", args=[reseller.code])
            ),
        },
    )


@login_required
@role_required("OWNER")
@require_POST
def verify_license_view(request):
    """Check a pasted licence key and report the result as a message."""
    result = verify_license(request.POST.get("key", ""))
    if result["valid"]:
        messages.success(
            request, f"Licence valid for {result['seats']} seats until {result['expires_at']:%Y-%m-%d}."
        )
    else:
        messages.error(request, f"Licence not valid ({result['reason']}).")
    return redirect(f"{reverse('partners:settings')}?tab=branding")
