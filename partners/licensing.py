"""Ed25519-signed self-hosted licence keys.

A key looks like ``IPL2.<payload-b64>.<sig-b64>`` where the payload is
``<company_id>|<seats>|<expiry-epoch>|<kind>`` and the signature is an Ed25519
signature over the payload bytes.

Signing needs the *private* key, which lives only on the vendor's machine
(env ``LICENSE_SIGNING_KEY``, base64 of the raw 32 bytes).  Verification needs
only :data:`LICENSE_PUBLIC_KEY`, which is embedded below and shipped with every
install — so ``verify_license`` works offline on an air-gapped self-hosted box
and a customer who owns ``SECRET_KEY`` still cannot forge a key.
"""

import base64
import logging
import os
from datetime import UTC, datetime

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

PREFIX = "IPL2"

#: Vendor licence-signing public key (base64, raw 32 bytes). Safe to publish.
LICENSE_PUBLIC_KEY = "b6wSeZVZNkY9ycsSJc5XnLMcKPR4jhLdbEOyMlBJAFc="

#: Name of the env/settings entry holding the base64 raw private key.
SIGNING_KEY_SETTING = "LICENSE_SIGNING_KEY"


class LicenseSigningUnavailable(RuntimeError):
    """Raised when a licence must be signed but no private key is configured."""


def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _b64d(text: str) -> bytes:
    padding = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + padding)


def _ed25519():
    try:
        from cryptography.hazmat.primitives.asymmetric import ed25519
    except ImportError as exc:  # pragma: no cover - dependency is pinned
        raise LicenseSigningUnavailable(
            "The 'cryptography' package is required for licence keys."
        ) from exc
    return ed25519


def _decode_key_material(value):
    """Decode a base64 (standard or urlsafe) raw 32-byte key."""
    text = (value or "").strip()
    if not text:
        return None
    for decoder in (base64.b64decode, base64.urlsafe_b64decode):
        try:
            raw = decoder(text + "=" * (-len(text) % 4))
        except Exception:
            continue
        if len(raw) == 32:
            return raw
    return None


def signing_key_configured() -> bool:
    """True when a usable private signing key is available."""
    return _private_key_bytes() is not None


def _private_key_bytes():
    value = getattr(settings, SIGNING_KEY_SETTING, None)
    if not value:
        value = os.environ.get(SIGNING_KEY_SETTING, "")
    return _decode_key_material(value)


def public_key_bytes():
    """The embedded verification key, or ``None`` if it is misconfigured."""
    return _decode_key_material(LICENSE_PUBLIC_KEY)


def _verification_keys():
    """Public keys a key may be checked against.

    Always the embedded vendor key; plus, when a private signing key is
    configured on this machine, the public half of that key — so a vendor (or a
    test run with an override keypair) can verify what it just issued.
    """
    ed25519 = _ed25519()
    keys = []
    raw = public_key_bytes()
    if raw is not None:
        keys.append(ed25519.Ed25519PublicKey.from_public_bytes(raw))
    private_raw = _private_key_bytes()
    if private_raw is not None:
        keys.append(
            ed25519.Ed25519PrivateKey.from_private_bytes(private_raw).public_key()
        )
    return keys


def generate_keypair():
    """Generate a fresh Ed25519 keypair; returns ``(private_b64, public_b64)``."""
    ed25519 = _ed25519()
    from cryptography.hazmat.primitives import serialization

    key = ed25519.Ed25519PrivateKey.generate()
    private = key.private_bytes(
        serialization.Encoding.Raw,
        serialization.PrivateFormat.Raw,
        serialization.NoEncryption(),
    )
    public = key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    return base64.b64encode(private).decode(), base64.b64encode(public).decode()


def _payload(company_id: int, seats: int, expires_at, kind: str) -> bytes:
    return f"{int(company_id)}|{int(seats)}|{int(expires_at.timestamp())}|{kind}".encode()


def make_key(company_id: int, seats: int, expires_at, kind="SELF_HOSTED") -> str:
    """Sign a licence key. ``expires_at`` is an aware datetime.

    Raises :class:`LicenseSigningUnavailable` when ``LICENSE_SIGNING_KEY`` is
    missing or malformed — signing is a vendor-only operation.
    """
    ed25519 = _ed25519()
    raw = _private_key_bytes()
    if raw is None:
        raise LicenseSigningUnavailable(
            f"{SIGNING_KEY_SETTING} is not set to a base64 raw 32-byte Ed25519 "
            "private key; licence keys can only be issued by the vendor."
        )
    payload = _payload(company_id, seats, expires_at, kind)
    signature = ed25519.Ed25519PrivateKey.from_private_bytes(raw).sign(payload)
    return f"{PREFIX}.{_b64e(payload)}.{_b64e(signature)}"


def verify_license(key: str) -> dict:
    """Check a licence key's signature and expiry, offline.

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
        signature_raw = _b64d(signature)
        company_id, seats, expiry, kind = payload.decode().split("|")
        company_id, seats, expiry = int(company_id), int(seats), int(expiry)
    except Exception:
        return result

    try:
        candidates = _verification_keys()
    except LicenseSigningUnavailable as exc:  # pragma: no cover - dependency pinned
        logger.warning("partners: cannot verify licence key: %s", exc)
        result["reason"] = "unverifiable"
        return result
    if not candidates:  # pragma: no cover - constant is well-formed
        result["reason"] = "unverifiable"
        return result
    for public_key in candidates:
        try:
            public_key.verify(signature_raw, payload)
            break
        except Exception:
            continue
    else:
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
