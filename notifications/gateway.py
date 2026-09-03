"""External-service adapters for the notifications app.

WhatsApp Business Cloud API. Environment: ``WHATSAPP_TOKEN``, ``WHATSAPP_PHONE_ID``.

``configured()`` is False until both env vars are set, so callers degrade
gracefully and tests never touch the network.
"""

import logging

from django.conf import settings

logger = logging.getLogger(__name__)

GRAPH_VERSION = "v20.0"
GRAPH_BASE = "https://graph.facebook.com"
TIMEOUT = 10


class GatewayError(RuntimeError):
    """The provider rejected the request or could not be reached."""


class NotConfigured(GatewayError):
    """Credentials for the provider are missing."""


def token() -> str:
    return (getattr(settings, "WHATSAPP_TOKEN", "") or "").strip()


def phone_id() -> str:
    return (getattr(settings, "WHATSAPP_PHONE_ID", "") or "").strip()


def configured() -> bool:
    """True when this gateway has everything it needs to call out."""
    return bool(token() and phone_id())


def verify_token() -> str:
    """Token the Meta webhook subscription must echo back."""
    return (getattr(settings, "WHATSAPP_VERIFY_TOKEN", "") or "").strip() or token()


def endpoint() -> str:
    return f"{GRAPH_BASE}/{GRAPH_VERSION}/{phone_id()}/messages"


def normalise_phone(phone: str) -> str:
    """Digits-only E.164-ish form the Cloud API expects (no '+', no spaces)."""
    if not phone:
        return ""
    cleaned = "".join(ch for ch in str(phone) if ch.isdigit())
    return cleaned


def build_payload(to, body="", template_name="", language="en_US", components=None) -> dict:
    """The JSON body for a text or template message."""
    payload = {"messaging_product": "whatsapp", "to": normalise_phone(to)}
    if template_name:
        template = {"name": template_name, "language": {"code": language}}
        if components:
            template["components"] = components
        payload["type"] = "template"
        payload["template"] = template
    else:
        payload["type"] = "text"
        payload["text"] = {"preview_url": False, "body": body}
    return payload


def send_whatsapp(to, body="", template_name="", language="en_US", components=None) -> dict:
    """POST one message to the Cloud API and return ``{"payload", "provider_ref"}``."""
    if not configured():
        raise NotConfigured("WhatsApp is not configured (set WHATSAPP_TOKEN and WHATSAPP_PHONE_ID).")
    if not normalise_phone(to):
        raise GatewayError("No usable phone number for this recipient.")

    import requests

    payload = build_payload(
        to, body=body, template_name=template_name, language=language, components=components
    )
    try:
        response = requests.post(
            endpoint(),
            json=payload,
            headers={"Authorization": f"Bearer {token()}"},
            timeout=TIMEOUT,
        )
    except Exception as exc:  # network errors, DNS, timeouts
        raise GatewayError(f"WhatsApp request failed: {exc}") from exc

    try:
        status_code = int(getattr(response, "status_code", 0) or 0)
    except (TypeError, ValueError):
        status_code = 0
    try:
        data = response.json()
    except Exception:
        data = {}
    if status_code >= 400:
        detail = (data.get("error") or {}).get("message") or f"HTTP {status_code}"
        raise GatewayError(f"WhatsApp rejected the message: {detail}")

    messages = data.get("messages") or []
    provider_ref = messages[0].get("id", "") if messages else ""
    return {"payload": payload, "response": data, "provider_ref": provider_ref}


def status_from_webhook(value: str) -> str:
    """Map a Cloud API status string onto an ``OutboundMessage`` status."""
    from notifications.models import OutboundMessage

    return {
        "sent": OutboundMessage.SENT,
        "delivered": OutboundMessage.DELIVERED,
        "read": OutboundMessage.READ,
        "failed": OutboundMessage.FAILED,
    }.get((value or "").lower(), "")
