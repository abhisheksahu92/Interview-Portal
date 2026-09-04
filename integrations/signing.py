"""HMAC-SHA256 request signing for outbound webhooks.

Every delivery carries four headers::

    X-IP-Event        the event name, e.g. "application.hired"
    X-IP-Delivery-Id  the WebhookDelivery primary key (for idempotency)
    X-IP-Timestamp    unix seconds, as a string
    X-IP-Signature    hex HMAC-SHA256 over "<timestamp>.<body>" keyed by the
                      webhook's secret

The signed string interpolates the timestamp so a captured body cannot be
replayed with a fresh timestamp, and receivers should reject timestamps outside
a few minutes of their own clock (``max_age_seconds`` below).
"""

import hashlib
import hmac

SIGNATURE_HEADER = "X-IP-Signature"
TIMESTAMP_HEADER = "X-IP-Timestamp"
EVENT_HEADER = "X-IP-Event"
DELIVERY_HEADER = "X-IP-Delivery-Id"

#: Receivers should treat anything older than this as a replay.
DEFAULT_MAX_AGE_SECONDS = 300


def _as_bytes(value):
    if isinstance(value, bytes):
        return value
    return str(value).encode()


def signed_payload(timestamp, body) -> bytes:
    """The exact byte string that gets signed: ``timestamp + "." + body``."""
    return _as_bytes(timestamp) + b"." + _as_bytes(body)


def build_signature(secret, timestamp, body) -> str:
    """Hex HMAC-SHA256 of ``timestamp.body`` keyed by ``secret``."""
    return hmac.new(
        _as_bytes(secret), signed_payload(timestamp, body), hashlib.sha256
    ).hexdigest()


def verify_signature(secret, timestamp, body, signature, max_age_seconds=None) -> bool:
    """True when ``signature`` matches ``secret``/``timestamp``/``body``.

    Compared in constant time. Pass ``max_age_seconds`` (or rely on
    :data:`DEFAULT_MAX_AGE_SECONDS` by passing it explicitly) to also reject
    stale timestamps; by default only the signature is checked so the helper
    stays usable in tests that pin a timestamp.
    """
    if not secret or not signature:
        return False
    expected = build_signature(secret, timestamp, body)
    if not hmac.compare_digest(expected, str(signature)):
        return False
    if max_age_seconds is not None:
        import time

        try:
            age = abs(time.time() - float(timestamp))
        except (TypeError, ValueError):
            return False
        if age > max_age_seconds:
            return False
    return True
