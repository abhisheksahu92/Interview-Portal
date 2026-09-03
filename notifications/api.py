"""The single entrypoint every other app uses to notify someone.

    from notifications import send

    send("application_received", application.candidate, {"application": application})

``send`` resolves the recipient, picks channels from the company's
``NotificationPreference`` (falling back to a computed default), renders the
event's templates and delivers synchronously, recording one
``OutboundMessage`` per channel. It never raises for a delivery problem — a
broken provider must not break the business action that triggered it.
"""

import logging

from django.conf import settings
from django.core import signing
from django.template.loader import render_to_string
from django.urls import reverse

from notifications import channels as channel_impl
from notifications import gateway, registry
from notifications.models import CandidateChannelOptOut, NotificationPreference, OutboundMessage

logger = logging.getLogger(__name__)

UNSUBSCRIBE_SALT = "notifications.unsubscribe"
MAX_ATTEMPTS = 3


class Recipient:
    """Normalised delivery target: email, phone, name and optional candidate profile."""

    __slots__ = ("email", "phone", "name", "profile", "user")

    def __init__(self, email="", phone="", name="", profile=None, user=None):
        self.email = (email or "").strip()
        self.phone = (phone or "").strip()
        self.name = (name or "").strip() or self.email or self.phone
        self.profile = profile
        self.user = user

    def __repr__(self):  # pragma: no cover - debugging aid
        return f"<Recipient {self.email or self.phone}>"


def resolve_recipient(recipient) -> Recipient:
    """Accept a User, CandidateProfile, email string or dict and normalise it."""
    if recipient is None:
        return Recipient()
    if isinstance(recipient, Recipient):
        return recipient
    if isinstance(recipient, str):
        value = recipient.strip()
        if "@" in value:
            return Recipient(email=value)
        return Recipient(phone=value)
    if isinstance(recipient, dict):
        return Recipient(
            email=recipient.get("email", ""),
            phone=recipient.get("phone", ""),
            name=recipient.get("name", ""),
            profile=recipient.get("profile"),
            user=recipient.get("user"),
        )

    # CandidateProfile: has a phone and a one-to-one user.
    if hasattr(recipient, "phone") and hasattr(recipient, "user"):
        user = recipient.user
        return Recipient(
            email=getattr(user, "email", "") or "",
            phone=recipient.phone or "",
            name=getattr(user, "get_full_name", lambda: "")() or getattr(user, "email", ""),
            profile=recipient,
            user=user,
        )

    # core.User: may have a candidate profile hanging off it.
    if hasattr(recipient, "email"):
        profile = getattr(recipient, "candidate_profile", None)
        return Recipient(
            email=recipient.email or "",
            phone=getattr(profile, "phone", "") or "",
            name=getattr(recipient, "get_full_name", lambda: "")() or recipient.email,
            profile=profile,
            user=recipient,
        )

    raise TypeError(f"Cannot use {recipient!r} as a notification recipient")


def has_feature(company, name):
    """``billing.entitlements.has_feature`` when billing is available, else False."""
    if company is None:
        return False
    try:
        from billing.entitlements import has_feature as _has_feature
    except Exception:  # pragma: no cover - billing always present in this project
        return False
    try:
        return bool(_has_feature(company, name))
    except Exception:
        logger.debug("Feature check for %s failed", name, exc_info=True)
        return False


def opted_out(recipient: Recipient, channel: str) -> bool:
    """True when this candidate has opted out of ``channel``."""
    if recipient.profile is None or recipient.profile.pk is None:
        return False
    return CandidateChannelOptOut.objects.filter(
        profile=recipient.profile, channel=channel
    ).exists()


def opted_out_of_event(recipient: Recipient, channel: str, event_name: str) -> bool:
    """True when this candidate should not get ``event_name`` on ``channel``.

    Beyond a whole-channel opt-out, a candidate can silence *non-essential*
    email (marketing/status chatter) while still receiving the transactional
    mail listed in ``registry.ESSENTIAL_EVENTS``.
    """
    if opted_out(recipient, channel):
        return True
    if channel != registry.EMAIL or registry.is_essential(event_name):
        return False
    return opted_out(recipient, registry.MARKETING_EMAIL)


def default_channels(event: registry.Event, company, recipient: Recipient) -> "list[str]":
    """Channels used when the company has no stored preference for the event.

    Email is always on. WhatsApp is on when the plan includes the ``whatsapp``
    feature and we actually have a phone number for the recipient.
    """
    selected = [registry.EMAIL]
    if (
        registry.WHATSAPP in event.channels
        and recipient.phone
        and has_feature(company, "whatsapp")
    ):
        selected.append(registry.WHATSAPP)
    return selected


def preference_channels(event_name, company):
    """The stored channel list for ``(company, event)``, or None when unset."""
    if company is None:
        return None
    preference = NotificationPreference.objects.filter(
        company=company, event=event_name
    ).first()
    if preference is None:
        return None
    return [c for c in preference.channels if c in registry.CHANNELS]


def set_preference(company, event_name, channels):
    """Store the channel list for one event (used by the settings UI)."""
    registry.get_event(event_name)
    cleaned = [c for c in registry.CHANNELS if c in set(channels or ())]
    preference, _ = NotificationPreference.objects.update_or_create(
        company=company, event=event_name, defaults={"channels": cleaned}
    )
    return preference


def effective_channels(company, event_name, recipient=None):
    """What ``send`` would use for this company/event, honouring stored prefs."""
    event = registry.get_event(event_name)
    recipient = recipient if isinstance(recipient, Recipient) else Recipient(phone="stub")
    stored = preference_channels(event_name, company)
    if stored is None:
        return default_channels(event, company, recipient)
    return stored


def unsubscribe_token(profile, channel=registry.WHATSAPP) -> str:
    return signing.dumps({"p": profile.pk, "c": channel}, salt=UNSUBSCRIBE_SALT)


def read_unsubscribe_token(token, max_age=60 * 60 * 24 * 90):
    """Return ``(profile_pk, channel)`` or raise ``signing.BadSignature``."""
    data = signing.loads(token, salt=UNSUBSCRIBE_SALT, max_age=max_age)
    return data["p"], data.get("c", registry.WHATSAPP)


def unsubscribe_url(recipient: Recipient, channel=registry.WHATSAPP) -> str:
    """Absolute opt-out link, or the settings page when there is no profile."""
    base = (getattr(settings, "SITE_URL", "") or "").rstrip("/")
    if recipient.profile is None or recipient.profile.pk is None:
        return f"{base}{reverse('notifications:settings')}"
    path = reverse(
        "notifications:unsubscribe", kwargs={"token": unsubscribe_token(recipient.profile, channel)}
    )
    return f"{base}{path}"


def build_context(event: registry.Event, recipient: Recipient, context, company):
    """Template context: caller values plus the standard extras."""
    full = {
        "site_name": "Interview Portal",
        "site_url": (getattr(settings, "SITE_URL", "") or "").rstrip("/"),
        "event": event.name,
        "event_label": event.label,
    }
    full.update(context or {})
    full.setdefault("company", company)
    full["recipient"] = recipient
    full["recipient_name"] = recipient.name
    # The footer link lands on the preference page defaulted to non-essential
    # email, since that is the choice an email reader is looking for.
    full.setdefault(
        "unsubscribe_url", unsubscribe_url(recipient, registry.MARKETING_EMAIL)
    )
    return full


def render_message(event: registry.Event, channel, context):
    """Render subject/text/html/whatsapp bodies for one channel."""
    prefix = f"notifications/{event.template_prefix}"
    rendered = {"subject": "", "text": "", "html": "", "whatsapp": ""}

    if channel == registry.WHATSAPP:
        try:
            rendered["whatsapp"] = render_to_string(f"{prefix}.whatsapp.txt", context).strip()
        except Exception:
            rendered["whatsapp"] = render_to_string(f"{prefix}.txt", context).strip()
        rendered["text"] = rendered["whatsapp"]
        rendered["subject"] = _render_subject(prefix, context, event)
        return rendered

    rendered["subject"] = _render_subject(prefix, context, event)
    rendered["text"] = render_to_string(f"{prefix}.txt", context)
    try:
        rendered["html"] = render_to_string(f"{prefix}.html", context)
    except Exception:
        logger.debug("No HTML part for %s", event.name)
    return rendered


def _render_subject(prefix, context, event):
    override = context.get("subject")
    if override:
        return str(override)
    try:
        return " ".join(render_to_string(f"{prefix}.subject.txt", context).split())
    except Exception:
        return event.label


def render_all(event_name, context=None, channel=registry.EMAIL):
    """Public render helper (used by tests and the preview/test-send button)."""
    event = registry.get_event(event_name)
    recipient = Recipient(email="preview@example.com", phone="919999999999", name="Preview")
    full = build_context(event, recipient, context or {}, (context or {}).get("company"))
    return render_message(event, channel, full)


def _infer_company(context, recipient):
    for key in ("company",):
        candidate = (context or {}).get(key)
        if candidate is not None and hasattr(candidate, "pk") and hasattr(candidate, "name"):
            return candidate
    application = (context or {}).get("application")
    if application is not None:
        company = getattr(application, "company", None)
        if company is not None:
            return company
    return None


def _consume_usage(company, channel):
    """Meter a WhatsApp message. A missing/incomplete billing app = unlimited."""
    if channel != registry.WHATSAPP or company is None:
        return True, ""
    try:
        from billing import usage as billing_usage
    except Exception:
        return True, ""
    consume = getattr(billing_usage, "consume", None)
    if consume is None:
        return True, ""
    quota_exceeded = getattr(billing_usage, "QuotaExceeded", None)
    try:
        consume(company, "WHATSAPP_MSG")
    except Exception as exc:
        if quota_exceeded is not None and isinstance(exc, quota_exceeded):
            return False, f"WhatsApp quota exceeded: {exc}"
        logger.debug("Usage metering unavailable", exc_info=True)
        return True, ""
    return True, ""


def _validate(channel, recipient: Recipient, company, event_name=""):
    """Reason this channel cannot be used, or "" when it can."""
    if channel not in registry.CHANNELS:
        return f"Unknown channel {channel!r}."
    if channel == registry.EMAIL and not recipient.email:
        return "No email address for this recipient."
    if channel == registry.WHATSAPP:
        if not recipient.phone:
            return "No phone number for this recipient."
        if not has_feature(company, "whatsapp"):
            return "The company's plan does not include WhatsApp."
        if not gateway.configured():
            return "WhatsApp is not configured."
    if opted_out(recipient, channel):
        return f"The recipient has opted out of {channel}."
    if event_name and opted_out_of_event(recipient, channel, event_name):
        return "The recipient has opted out of non-essential email."
    return ""


def deliver(message: OutboundMessage, context=None):
    """(Re)attempt delivery of an existing OutboundMessage row."""
    event = registry.get_event(message.event)
    context = context or {}
    message.attempts = (message.attempts or 0) + 1
    try:
        rendered = {
            "subject": message.subject,
            "text": message.body,
            "html": context.get("html", ""),
            "whatsapp": message.body,
        }
        if context:
            rendered = render_message(event, message.channel, context)
            message.subject = rendered["subject"][:255]
            message.body = rendered["text"]
        allowed, reason = _consume_usage(message.company, message.channel)
        if not allowed:
            message.attempts -= 1
            return message.mark_skipped(reason)
        result = channel_impl.get_sender(message.channel)(message, rendered, context)
    except Exception as exc:
        logger.warning(
            "Notification %s via %s failed: %s", message.event, message.channel, exc, exc_info=True
        )
        return message.mark_failed(exc)
    payload = dict(message.payload or {})
    payload.update(result.get("payload") or {})
    message.payload = payload
    return message.mark_sent(result.get("provider_ref", ""))


def send(event: str, recipient, context: dict, company=None, channels=None):
    """Notify ``recipient`` about ``event``; returns the OutboundMessage rows.

    ``recipient`` may be a ``core.User``, a ``jobs.CandidateProfile``, an email
    string, or a dict with ``email``/``phone``/``name`` keys. ``channels``
    overrides both the company preference and the computed default.
    """
    event_obj = registry.get_event(event)
    context = dict(context or {})
    target = resolve_recipient(recipient)
    if company is None:
        company = _infer_company(context, target)

    if channels is None:
        selected = preference_channels(event, company)
        if selected is None:
            selected = default_channels(event_obj, company, target)
    else:
        selected = [c for c in channels]

    messages = []
    for channel in selected:
        message = OutboundMessage.objects.create(
            company=company if getattr(company, "pk", None) else None,
            recipient_email=target.email,
            recipient_phone=target.phone,
            channel=channel,
            event=event,
            status=OutboundMessage.QUEUED,
        )
        reason = _validate(channel, target, company, event)
        if reason:
            messages.append(message.mark_skipped(reason))
            continue
        full_context = build_context(event_obj, target, context, company)
        if channel == registry.WHATSAPP and event_obj.whatsapp_template_name:
            full_context.setdefault("template_name", event_obj.whatsapp_template_name)
        messages.append(deliver(message, full_context))
    return messages
