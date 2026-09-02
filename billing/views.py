"""Billing UI: plan overview, Stripe Checkout / Portal redirects, webhook."""

import logging

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from billing import gateway, webhooks
from billing.limits import usage
from billing.models import Plan
from billing.services import get_subscription, pro_plan
from core.models import Membership
from core.permissions import role_required

logger = logging.getLogger(__name__)


@login_required
@role_required(Membership.OWNER, Membership.RECRUITER)
def overview(request):
    context = usage(request.company)
    context["plans"] = list(Plan.objects.all())
    context["pro_plan"] = pro_plan()
    context["stripe_ready"] = gateway.is_configured() and bool(settings.STRIPE_PRICE_ID_PRO)
    context["is_owner"] = request.user.role_in(request.company) == Membership.OWNER
    return render(request, "billing/overview.html", context)


@login_required
@role_required(Membership.OWNER)
@require_POST
def checkout(request):
    subscription = get_subscription(request.company)
    plan = pro_plan()
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
