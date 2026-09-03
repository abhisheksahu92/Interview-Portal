"""HMAC-signed self-hosted licence keys.

A key looks like ``IPL.<payload-b64>.<sig-b64>`` where the payload is
``<company_id>|<seats>|<expiry-epoch>|<kind>`` and the signature is
HMAC-SHA256 over the payload using ``settings.SECRET_KEY``.  No database access
is needed to check a key's integrity, so ``verify_license`` works on an
air-gapped self-hosted install too.
"""

import base64
import hashlib
import hmac
from datetime import UTC, datetime

from django.conf import settings
from django.utils import timezone

PREFIX = "IPL"


def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _b64d(text: str) -> bytes:
    padding = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + padding)


def _sign(payload: bytes) -> str:
    digest = hmac.new(settings.SECRET_KEY.encode(), payload, hashlib.sha256).digest()
    return _b64e(digest)


def make_key(company_id: int, seats: int, expires_at, kind="SELF_HOSTED") -> str:
    """Build a signed licence key. ``expires_at`` is an aware datetime."""
    payload = f"{int(company_id)}|{int(seats)}|{int(expires_at.timestamp())}|{kind}".encode()
    return f"{PREFIX}.{_b64e(payload)}.{_sign(payload)}"


def verify_license(key: str) -> dict:
    """Check a licence key's signature and expiry.

    Returns ``{"valid", "reason", "company_id", "seats", "expires_at", "kind"}``.
    Never raises: a malformed key is simply invalid.
    """
    result = {
        "valid": False,
        "reason": "malformed",
        "company_id": None,
        "seats": None,
        "expires_at": None,
        "kind": None,
    }
    if not key or not isinstance(key, str):
        return result
    parts = key.strip().split(".")
    if len(parts) != 3 or parts[0] != PREFIX:
        return result
    _, body, signature = parts
    try:
        payload = _b64d(body)
        company_id, seats, expiry, kind = payload.decode().split("|")
        company_id, seats, expiry = int(company_id), int(seats), int(expiry)
    except Exception:
        return result
    if not hmac.compare_digest(_sign(payload), signature):
        result["reason"] = "bad-signature"
        return result
    expires_at = datetime.fromtimestamp(expiry, tz=UTC)
    result.update(
        company_id=company_id, seats=seats, expires_at=expires_at, kind=kind, reason="ok"
    )
    if expires_at <= timezone.now():
        result["reason"] = "expired"
        return result
    result["valid"] = True
    return result


def issue_license(company, seats=5, days=365, kind="SELF_HOSTED"):
    """Create and persist a :class:`partners.models.License` for ``company``."""
    from datetime import timedelta

    from partners.models import License

    expires_at = timezone.now() + timedelta(days=int(days))
    key = make_key(company.pk, seats, expires_at, kind=kind)
    return License.objects.create(
        company=company, kind=kind, key=key, seats=seats, expires_at=expires_at
    )
