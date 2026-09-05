"""Adapters for the background-verification vendor.

Same contract as every other Phase 3/4 gateway: read keys from the environment,
report a clear "not configured" state when they are missing, and never touch the
network in tests.

Two adapters ship:

``MockProvider``
    Used whenever ``BGV_API_KEY`` is empty — i.e. the default install and the
    whole test suite. It accepts submissions, hands back a deterministic
    ``MOCK-<pk>`` reference and advances an order one step per poll
    (``SUBMITTED`` → ``IN_PROGRESS`` → ``COMPLETED`` with every check CLEAR), so
    `manage.py bgv_poll` makes the entire flow demoable with no vendor account.

``AuthBridgeLikeProvider``
    The shape a real Indian vendor (AuthBridge, IDfy, SpringVerify …) would take.
    It is deliberately inert: every call raises :class:`NotConfigured` until
    someone writes the HTTP calls against a real contract.

The webhook signature is HMAC-SHA256 over the raw request body, keyed with
``BGV_API_KEY`` and compared with :func:`hmac.compare_digest`. With no key
configured there is nothing to verify against, so the webhook refuses
everything — a mock install advances orders through ``bgv_poll`` instead.
"""

import hashlib
import hmac
import logging

from django.conf import settings

logger = logging.getLogger(__name__)

#: Header the vendor is expected to sign the body with.
SIGNATURE_HEADER = "HTTP_X_BGV_SIGNATURE"


class NotConfigured(RuntimeError):
    """The configured provider has no credentials, so it cannot be called."""


class BaseProvider:
    """Interface every BGV adapter implements."""

    name = "base"

    def configured(self) -> bool:
        raise NotImplementedError

    def submit(self, order) -> str:
        """Send ``order`` to the vendor; return their reference."""
        raise NotImplementedError

    def fetch_status(self, order) -> dict:
        """Poll the vendor; return ``{"state": ..., "checks": {...}}``."""
        raise NotImplementedError

    def verify_signature(self, body: bytes, signature: str) -> bool:
        raise NotImplementedError


def _api_key() -> str:
    return (getattr(settings, "BGV_API_KEY", "") or "").strip()


def _sign(body: bytes, key: str) -> str:
    return hmac.new(key.encode(), body or b"", hashlib.sha256).hexdigest()


class MockProvider(BaseProvider):
    """A deterministic in-process stand-in for a real vendor."""

    name = "mock"

    def configured(self) -> bool:
        return True

    def submit(self, order) -> str:
        return f"MOCK-{order.pk:06d}"

    def fetch_status(self, order) -> dict:
        """Advance exactly one step per poll, so a demo shows real motion."""
        model = type(order)
        if order.status == model.SUBMITTED:
            return {"state": model.IN_PROGRESS, "checks": {}}
        if order.status == model.IN_PROGRESS:
            checks = {
                code: {"status": model.CLEAR, "notes": "Verified against submitted records."}
                for code in (order.checks or [])
            }
            return {"state": model.COMPLETED, "checks": checks}
        return {"state": order.status, "checks": order.result or {}}

    def verify_signature(self, body: bytes, signature: str) -> bool:
        """No key, no trust: the mock provider never accepts a webhook."""
        return False


class AuthBridgeLikeProvider(BaseProvider):
    """Placeholder for a real vendor integration (AuthBridge/IDfy shaped)."""

    name = "authbridge"

    def __init__(self, api_key="", api_base=""):
        self.api_key = api_key or _api_key()
        self.api_base = api_base or (getattr(settings, "BGV_API_BASE", "") or "")

    def configured(self) -> bool:
        return bool(self.api_key and self.api_base)

    def submit(self, order):
        raise NotConfigured(
            "The AuthBridge-style BGV adapter is a stub: no vendor calls are implemented."
        )

    def fetch_status(self, order):
        raise NotConfigured(
            "The AuthBridge-style BGV adapter is a stub: no vendor calls are implemented."
        )

    def verify_signature(self, body: bytes, signature: str) -> bool:
        if not self.api_key or not signature:
            return False
        return hmac.compare_digest(_sign(body, self.api_key), str(signature).strip())


def get_provider():
    """The adapter this install should use.

    ``BGV_API_KEY`` empty (the default) → :class:`MockProvider`. Otherwise the
    provider named by ``BGV_PROVIDER``, defaulting to the AuthBridge-like one.
    """
    key = _api_key()
    name = (getattr(settings, "BGV_PROVIDER", "") or "").strip().lower()
    if name == "mock" or not key:
        return MockProvider()
    return AuthBridgeLikeProvider(api_key=key)


def provider_name() -> str:
    return get_provider().name


def is_live() -> bool:
    """True when a real vendor is wired up (not the mock)."""
    return not isinstance(get_provider(), MockProvider)


def verify_webhook(body: bytes, signature: str) -> bool:
    """Verify a webhook body against the configured provider's signing key."""
    try:
        return bool(get_provider().verify_signature(body, signature))
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("bgv: webhook signature check failed: %s", exc)
        return False


def sign_payload(body: bytes) -> str:
    """Test/ops helper: the signature the vendor would send for ``body``."""
    return _sign(body, _api_key())
