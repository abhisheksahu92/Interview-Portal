"""Notification settings UI, outbox log, candidate opt-out and the WhatsApp webhook."""

import json
import logging

from django.conf import settings
from django.contrib import messages as django_messages
from django.contrib.auth.decorators import login_required
from django.core import signing
from django.http import HttpResponse, HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from core.models import Membership
from core.permissions import role_required
from notifications import api, gateway, registry
from notifications.models import (
    CandidateChannelOptOut,
    NotificationPreference,
    OutboundMessage,
)

logger = logging.getLogger(__name__)

RECRUITER_ROLES = (Membership.OWNER, Membership.RECRUITER)
PAGE_SIZE = 50


def _matrix(company):
    """Rows of ``{event, cells:[{channel, enabled, supported}]}`` for the UI."""
    stored = {
        pref.event: [c for c in pref.channels if c in registry.CHANNELS]
        for pref in NotificationPreference.objects.for_company(company)
    }
    rows = []
    for event in registry.all_events():
        if event.name in stored:
            enabled = set(stored[event.name])
        else:
            # Default: email on, whatsapp on when the event and plan support it.
            enabled = {registry.EMAIL}
            if registry.WHATSAPP in event.channels and api.has_feature(company, "whatsapp"):
                enabled.add(registry.WHATSAPP)
        rows.append(
            {
                "event": event,
                "cells": [
                    {
                        "channel": channel,
                        "label": registry.CHANNEL_LABELS[channel],
                        "enabled": channel in enabled,
                        "supported": channel in event.channels,
                    }
                    for channel in registry.CHANNELS
                ],
            }
        )
    return rows


def _whatsapp_status(company):
    return {
        "configured": gateway.configured(),
        "entitled": api.has_feature(company, "whatsapp"),
        "phone_id": gateway.phone_id(),
        "webhook_url": (getattr(settings, "SITE_URL", "") or "").rstrip("/")
        + reverse("notifications:whatsapp_webhook"),
    }


@login_required
@role_required(*RECRUITER_ROLES)
def index(request):
    """Per-event × per-channel toggle matrix plus the WhatsApp status card."""
    context = {
        "rows": _matrix(request.company),
        "channels": [
            {"key": c, "label": registry.CHANNEL_LABELS[c]} for c in registry.CHANNELS
        ],
        "whatsapp": _whatsapp_status(request.company),
        "recent": OutboundMessage.objects.for_company(request.company)[:5],
    }
    return render(request, "notifications/settings.html", context)


@login_required
@role_required(*RECRUITER_ROLES)
@require_POST
def toggle(request, event, channel):
    """HTMX endpoint: flip one cell of the matrix and re-render that row."""
    try:
        event_obj = registry.get_event(event)
    except registry.UnknownEvent:
        return HttpResponseBadRequest("Unknown event.")
    if channel not in registry.CHANNELS:
        return HttpResponseBadRequest("Unknown channel.")

    current = set(api.effective_channels(request.company, event))
    if channel in current:
        current.discard(channel)
    else:
        current.add(channel)
    api.set_preference(request.company, event, current)

    row = next(r for r in _matrix(request.company) if r["event"].name == event_obj.name)
    return render(request, "notifications/_pref_row.html", {"row": row})


@login_required
@role_required(*RECRUITER_ROLES)
@require_POST
def test_send(request):
    """Send the selected event to the requesting user, on the given channels."""
    event = request.POST.get("event") or "application_received"
    channel = request.POST.get("channel") or registry.EMAIL
    try:
        registry.get_event(event)
    except registry.UnknownEvent:
        django_messages.error(request, "Unknown notification event.")
        return redirect("notifications:settings")

    recipient = {
        "email": request.user.email,
        "phone": request.POST.get("phone", "").strip(),
        "name": request.user.get_full_name() or request.user.email,
    }
    sent = api.send(
        event,
        recipient,
        {"company": request.company, "test_send": True},
        company=request.company,
        channels=[channel],
    )
    outcome = sent[0] if sent else None
    if outcome is None or outcome.status == OutboundMessage.FAILED:
        django_messages.error(
            request, f"Test {channel} failed: {getattr(outcome, 'error', 'no message created')}"
        )
    elif outcome.status == OutboundMessage.SKIPPED:
        django_messages.warning(request, f"Test {channel} skipped: {outcome.error}")
    else:
        django_messages.success(request, f"Test {channel} sent to {outcome.recipient}.")
    return redirect("notifications:settings")


@login_required
@role_required(*RECRUITER_ROLES)
def outbox(request):
    """Filterable delivery log."""
    queryset = OutboundMessage.objects.for_company(request.company)
    filters = {
        "event": request.GET.get("event", ""),
        "channel": request.GET.get("channel", ""),
        "status": request.GET.get("status", ""),
        "q": request.GET.get("q", "").strip(),
    }
    if filters["event"]:
        queryset = queryset.filter(event=filters["event"])
    if filters["channel"]:
        queryset = queryset.filter(channel=filters["channel"])
    if filters["status"]:
        queryset = queryset.filter(status=filters["status"])
    if filters["q"]:
        queryset = queryset.filter(recipient_email__icontains=filters["q"])

    context = {
        "messages_page": list(queryset[:PAGE_SIZE]),
        "filters": filters,
        "events": registry.all_events(),
        "channels": [
            {"key": c, "label": registry.CHANNEL_LABELS[c]} for c in registry.CHANNELS
        ],
        "statuses": OutboundMessage.STATUS_CHOICES,
    }
    return render(request, "notifications/outbox.html", context)


@login_required
@role_required(*RECRUITER_ROLES)
@require_POST
def resend(request, pk):
    """Re-attempt one logged message (no stored context, so the body is reused)."""
    message = get_object_or_404(
        OutboundMessage.objects.for_company(request.company), pk=pk
    )
    message.status = OutboundMessage.QUEUED
    api.deliver(message)
    if message.status == OutboundMessage.SENT:
        django_messages.success(request, "Message resent.")
    else:
        django_messages.error(request, f"Resend failed: {message.error}")
    if request.headers.get("HX-Request"):
        return render(request, "notifications/_outbox_row.html", {"message": message})
    return redirect("notifications:outbox")


def unsubscribe(request, token):
    """Candidate-facing opt-out link included in every email footer."""
    try:
        profile_pk, channel = api.read_unsubscribe_token(token)
    except signing.BadSignature:
        return render(
            request, "notifications/unsubscribe.html", {"invalid": True}, status=400
        )

    from jobs.models import CandidateProfile

    profile = get_object_or_404(CandidateProfile, pk=profile_pk)

    if request.method == "POST":
        target = request.POST.get("channel") or channel
        if target in registry.OPT_OUT_CHANNELS:
            if request.POST.get("resubscribe"):
                CandidateChannelOptOut.objects.filter(
                    profile=profile, channel=target
                ).delete()
            else:
                CandidateChannelOptOut.objects.get_or_create(
                    profile=profile, channel=target
                )

    current = set(
        CandidateChannelOptOut.objects.filter(profile=profile).values_list(
            "channel", flat=True
        )
    )
    return render(
        request,
        "notifications/unsubscribe.html",
        {
            "profile": profile,
            "channel": channel,
            "channel_label": registry.CHANNEL_LABELS.get(channel, channel),
            "opted_out": channel in current,
            "choices": [
                {
                    "channel": c,
                    "label": registry.CHANNEL_LABELS.get(c, c),
                    "opted_out": c in current,
                }
                for c in (registry.MARKETING_EMAIL, registry.WHATSAPP)
            ],
            "essential_events": sorted(registry.ESSENTIAL_EVENTS),
            "token": token,
        },
    )


@csrf_exempt
def whatsapp_webhook(request):
    """Meta webhook: GET verifies the subscription, POST carries status updates."""
    if request.method == "GET":
        mode = request.GET.get("hub.mode")
        token = request.GET.get("hub.verify_token")
        challenge = request.GET.get("hub.challenge", "")
        expected = gateway.verify_token()
        if mode == "subscribe" and expected and token == expected:
            return HttpResponse(challenge, content_type="text/plain")
        return HttpResponse("forbidden", status=403)

    if request.method != "POST":
        return HttpResponse(status=405)

    try:
        body = json.loads(request.body.decode("utf-8") or "{}")
    except (ValueError, UnicodeDecodeError):
        return HttpResponseBadRequest("Invalid JSON.")

    updated = 0
    for entry in body.get("entry") or []:
        for change in entry.get("changes") or []:
            for status in (change.get("value") or {}).get("statuses") or []:
                if _apply_status(status):
                    updated += 1
    return JsonResponse({"updated": updated})


def _apply_status(status):
    provider_ref = status.get("id") or ""
    mapped = gateway.status_from_webhook(status.get("status"))
    if not provider_ref or not mapped:
        return False
    message = OutboundMessage.objects.filter(provider_ref=provider_ref).first()
    if message is None:
        return False
    message.status = mapped
    error = (status.get("errors") or [{}])[0].get("title", "")
    if mapped == OutboundMessage.FAILED:
        message.error = error or "Reported failed by WhatsApp."
    message.save(update_fields=["status", "error"])
    return True
