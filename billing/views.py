"""Billing UI: plan overview, Razorpay/Stripe checkout, webhooks, invoices."""

import logging

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404, HttpResponse, HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from billing import gateway, invoicing, razorpay_gateway, webhooks
from billing import usage as usage_module
from billing.limits import usage as job_usage
from billing.models import Invoice, Plan, Subscription
from billing.services import get_subscription, pro_plan, sellable_plans
from core.models import Membership
from core.permissions import role_required

logger = logging.getLogger(__name__)

STRIPE = Subscription.STRIPE
RAZORPAY = Subscription.RAZORPAY


def provider_choice():
    """Which gateway the overview offers: Razorpay by default, else Stripe."""
    if razorpay_gateway.is_configured():
        return RAZORPAY
    if gateway.is_configured():
        return STRIPE
    return ""


@login_required
@role_required(Membership.OWNER, Membership.RECRUITER)
def overview(request):
    company = request.company
    subscription = get_subscription(company)
    from billing.entitlements import plan_for

    effective_plan = plan_for(company)
    context = job_usage(company)
    context.update(
        {
            "subscription": subscription,
            "plan": effective_plan,
            "billed_plan": subscription.plan,
            "in_trial": subscription.in_trial,
            "trial_days_left": subscription.trial_days_left,
            "usage_rows": usage_module.snapshot(company),
            "seats_used": subscription.seats_used,
            "max_seats": effective_plan.max_seats,
            "plans": sellable_plans(),
            "pro_plan": pro_plan(),
            "invoices": list(Invoice.objects.filter(company=company)[:24]),
            "placement_fees": list(
                company.placement_fees.select_related("application__job")[:24]
            ),
            "provider": provider_choice(),
            "razorpay_ready": razorpay_gateway.is_configured(),
            "stripe_ready": gateway.is_configured() and bool(settings.STRIPE_PRICE_ID_PRO),
            "interval": (
                Subscription.YEARLY
                if request.GET.get("interval") == Subscription.YEARLY
                else Subscription.MONTHLY
            ),
            "intervals": Subscription.INTERVAL_CHOICES,
            "is_owner": request.user.role_in(company) == Membership.OWNER,
        }
    )
    context["not_configured"] = not context["provider"]
    return render(request, "billing/overview.html", context)


@login_required
@role_required(Membership.OWNER)
@require_POST
def billing_details(request):
    """Owner-only GSTIN + billing address form."""
    subscription = get_subscription(request.company)
    subscription.gstin = (request.POST.get("gstin") or "").strip().upper()
    subscription.billing_address = {
        "line1": (request.POST.get("line1") or "").strip(),
        "line2": (request.POST.get("line2") or "").strip(),
        "city": (request.POST.get("city") or "").strip(),
        "state": (request.POST.get("state") or "").strip(),
        "state_code": (request.POST.get("state_code") or "").strip(),
        "postal_code": (request.POST.get("postal_code") or "").strip(),
        "country": (request.POST.get("country") or "India").strip(),
    }
    subscription.save(update_fields=["gstin", "billing_address", "updated_at"])
    messages.success(request, "Billing details saved.")
    return redirect("billing:overview")


def _requested_plan(request, default_code=Plan.GROWTH):
    code = (request.POST.get("plan") or request.GET.get("plan") or default_code).upper()
    plan = Plan.objects.filter(code=code, code__in=Plan.PAID_CODES).first()
    return plan


def _requested_interval(request):
    interval = (request.POST.get("interval") or request.GET.get("interval") or "").upper()
    return Subscription.YEARLY if interval == Subscription.YEARLY else Subscription.MONTHLY


# --- Razorpay ------------------------------------------------------------


@login_required
@role_required(Membership.OWNER)
@require_POST
def razorpay_checkout(request):
    """Create a Razorpay subscription (monthly) or order (yearly) and pay it."""
    subscription = get_subscription(request.company)
    plan = _requested_plan(request)
    interval = _requested_interval(request)
    if plan is None:
        messages.error(request, "Choose a plan to upgrade to.")
        return redirect("billing:overview")
    if not razorpay_gateway.is_configured():
        messages.error(request, "Razorpay is not configured on this server.")
        return redirect("billing:overview")

    try:
        if interval == Subscription.YEARLY:
            remote = razorpay_gateway.create_order(
                company=request.company, plan=plan, interval=interval
            )
            is_subscription = False
        else:
            remote = razorpay_gateway.create_subscription(
                company=request.company, plan=plan, interval=interval
            )
            is_subscription = True
    except razorpay_gateway.RazorpayUnavailable as exc:
        logger.warning("billing: razorpay unavailable: %s", exc)
        messages.error(request, "Razorpay is not available right now.")
        return redirect("billing:overview")

    subscription.provider = RAZORPAY
    subscription.interval = interval
    if is_subscription:
        subscription.razorpay_subscription_id = remote["id"]
    subscription.save()

    options = razorpay_gateway.checkout_options(
        company=request.company,
        plan=plan,
        interval=interval,
        ref=remote["id"],
        subscription=is_subscription,
    )
    return render(
        request,
        "billing/razorpay_checkout.html",
        {
            "options": options,
            "plan": plan,
            "interval": interval,
            "is_subscription": is_subscription,
            "amount_inr": plan.price_for(interval),
            "verify_url": reverse("billing:razorpay_verify"),
        },
    )


@login_required
@role_required(Membership.OWNER)
@require_POST
def razorpay_verify(request):
    """Verify the Checkout callback signature and activate the plan."""
    subscription = get_subscription(request.company)
    plan = _requested_plan(request, default_code=subscription.plan.code)
    payment_id = request.POST.get("razorpay_payment_id") or ""
    order_id = request.POST.get("razorpay_order_id") or ""
    remote_sub_id = request.POST.get("razorpay_subscription_id") or ""
    signature = request.POST.get("razorpay_signature") or ""
    try:
        razorpay_gateway.verify_payment_signature(
            order_id=order_id or None,
            payment_id=payment_id,
            signature=signature,
            subscription_id=remote_sub_id or None,
        )
    except (razorpay_gateway.SignatureInvalid, razorpay_gateway.RazorpayUnavailable) as exc:
        logger.warning("billing: razorpay payment rejected: %s", exc)
        return JsonResponse({"ok": False, "error": "signature verification failed"}, status=400)

    if plan is not None:
        subscription.plan = plan
    subscription.provider = RAZORPAY
    subscription.status = Subscription.ACTIVE
    subscription.past_due_since = None
    subscription.trial_ends_at = None
    if remote_sub_id:
        subscription.razorpay_subscription_id = remote_sub_id
    subscription.save()
    return JsonResponse({"ok": True, "redirect": reverse("billing:overview") + "?upgraded=1"})


@csrf_exempt
def razorpay_webhook(request):
    if request.method != "POST":
        return HttpResponse(status=405)
    signature = request.META.get("HTTP_X_RAZORPAY_SIGNATURE", "")
    try:
        razorpay_gateway.verify_webhook_signature(request.body, signature)
    except razorpay_gateway.RazorpayUnavailable as exc:
        logger.warning("billing: razorpay webhook unavailable: %s", exc)
        return HttpResponse("razorpay not configured", status=503)
    except razorpay_gateway.SignatureInvalid as exc:
        logger.warning("billing: rejected razorpay webhook: %s", exc)
        return HttpResponse("invalid signature", status=400)

    import json

    try:
        event = json.loads(request.body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return HttpResponse("invalid payload", status=400)

    event_id = request.META.get("HTTP_X_RAZORPAY_EVENT_ID", "") or webhooks.event_fingerprint(
        request.body
    )
    webhooks.handle_razorpay_event(event, event_id=event_id)
    return HttpResponse(status=200)


# --- Invoices ------------------------------------------------------------


@login_required
@role_required(Membership.OWNER, Membership.RECRUITER)
def invoice_download(request, pk):
    invoice = get_object_or_404(Invoice, pk=pk, company=request.company)
    if not invoice.pdf:
        invoicing.render_pdf(invoice)
    if not invoice.pdf:
        raise Http404("No PDF available for this invoice.")
    return FileResponse(
        invoice.pdf.open("rb"),
        as_attachment=True,
        filename=f"{invoice.number.replace('/', '-')}.pdf",
        content_type="application/pdf",
    )


# --- Stripe (legacy / international) -------------------------------------


@login_required
@role_required(Membership.OWNER)
@require_POST
def checkout(request):
    subscription = get_subscription(request.company)
    plan = _requested_plan(request, default_code=Plan.PRO) or pro_plan()
    price_id = plan.stripe_price_id or settings.STRIPE_PRICE_ID_PRO
    if not price_id:
        messages.error(request, "Stripe is not configured yet (missing STRIPE_PRICE_ID_PRO).")
        return redirect("billing:overview")
    try:
        session = gateway.create_checkout_session(
            company=request.company,
            subscription=subscription,
            price_id=price_id,
            success_url=request.build_absolute_uri(reverse("billing:overview")) + "?upgraded=1",
            cancel_url=request.build_absolute_uri(reverse("billing:overview")),
        )
    except gateway.StripeUnavailable as exc:
        logger.warning("billing: checkout unavailable: %s", exc)
        messages.error(request, "Billing is not available right now.")
        return redirect("billing:overview")
    return HttpResponseRedirect(session["url"])


@login_required
@role_required(Membership.OWNER)
@require_POST
def portal(request):
    subscription = get_subscription(request.company)
    if not subscription.stripe_customer_id:
        messages.info(request, "You do not have a Stripe customer record yet.")
        return redirect("billing:overview")
    try:
        session = gateway.create_portal_session(
            subscription=subscription,
            return_url=request.build_absolute_uri(reverse("billing:overview")),
        )
    except gateway.StripeUnavailable as exc:
        logger.warning("billing: portal unavailable: %s", exc)
        messages.error(request, "Billing is not available right now.")
        return redirect("billing:overview")
    return HttpResponseRedirect(session["url"])


@csrf_exempt
def webhook(request):
    if request.method != "POST":
        return HttpResponse(status=405)
    signature = request.META.get("HTTP_STRIPE_SIGNATURE", "")
    try:
        event = gateway.construct_event(request.body, signature)
    except gateway.StripeUnavailable as exc:
        logger.warning("billing: webhook unavailable: %s", exc)
        return HttpResponse("stripe not configured", status=503)
    except Exception as exc:  # invalid payload or bad signature
        logger.warning("billing: rejected stripe webhook: %s", exc)
        return HttpResponse("invalid signature", status=400)

    webhooks.handle_event(event)
    return HttpResponse(status=200)
