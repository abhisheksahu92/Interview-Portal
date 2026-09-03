"""Channel implementations. Each takes a rendered message and delivers it.

A channel raises on failure; ``notifications.api`` records the outcome on the
``OutboundMessage`` row.
"""

import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives

from notifications import gateway, registry

logger = logging.getLogger(__name__)


class DeliveryError(RuntimeError):
    """Delivery failed on this channel."""


def send_email(message, rendered, context):
    """Deliver via Django mail; attachments come from ``context["attachments"]``.

    Attachments are ``(name, content, mimetype)`` triples.
    """
    if not message.recipient_email:
        raise DeliveryError("No email address for this recipient.")
    mail = EmailMultiAlternatives(
        subject=rendered["subject"],
        body=rendered["text"],
        from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "no-reply@localhost"),
        to=[message.recipient_email],
    )
    if rendered.get("html"):
        mail.attach_alternative(rendered["html"], "text/html")
    for attachment in context.get("attachments") or ():
        try:
            name, content, mimetype = attachment
        except (TypeError, ValueError):
            logger.warning("Ignoring malformed attachment %r", attachment)
            continue
        mail.attach(name, content, mimetype)
    sent = mail.send()
    if not sent:
        raise DeliveryError("The mail backend accepted 0 messages.")
    return {"provider_ref": "", "payload": {"to": message.recipient_email, "sent": sent}}


def send_whatsapp(message, rendered, context):
    """Deliver via the WhatsApp Cloud API (template message when asked for)."""
    if not message.recipient_phone:
        raise DeliveryError("No phone number for this recipient.")
    if not gateway.configured():
        raise DeliveryError("WhatsApp is not configured.")
    try:
        result = gateway.send_whatsapp(
            message.recipient_phone,
            body=rendered.get("whatsapp") or rendered.get("text", ""),
            template_name=context.get("template_name", "") or "",
            language=context.get("template_language", "en_US"),
            components=context.get("template_components"),
        )
    except gateway.GatewayError as exc:
        raise DeliveryError(str(exc)) from exc
    return {"provider_ref": result.get("provider_ref", ""), "payload": result.get("payload", {})}


def send_sms(message, rendered, context):
    """SMS stub: no provider is wired up yet, so this always reports failure."""
    raise DeliveryError("SMS delivery is not implemented yet (no provider configured).")


SENDERS = {
    registry.EMAIL: send_email,
    registry.WHATSAPP: send_whatsapp,
    registry.SMS: send_sms,
}


def get_sender(channel):
    try:
        return SENDERS[channel]
    except KeyError:
        raise DeliveryError(f"Unknown channel {channel!r}") from None
