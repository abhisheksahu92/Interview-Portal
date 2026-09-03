"""External e-sign adapter for the offers app (DocuSign-style, env-gated stub).

Environment variables:
    ESIGN_PROVIDER   provider key, e.g. ``docusign``
    ESIGN_API_BASE   API base URL
    ESIGN_ACCOUNT_ID account/tenant id
    ESIGN_API_KEY    integration secret

With any of them missing :func:`configured` is False and the built-in
click-to-sign flow is used instead. Nothing here ever touches the network in
tests: without credentials every call returns a "not configured" result.
"""

import os

PROVIDER_LABEL = "External e-sign"


def _env(name):
    return (os.environ.get(name) or "").strip()


def settings_snapshot() -> dict:
    return {
        "provider": _env("ESIGN_PROVIDER") or "docusign",
        "api_base": _env("ESIGN_API_BASE"),
        "account_id": _env("ESIGN_ACCOUNT_ID"),
        "api_key": _env("ESIGN_API_KEY"),
    }


def configured() -> bool:
    """True when this gateway has everything it needs to call out."""
    snapshot = settings_snapshot()
    return all(snapshot[key] for key in ("api_base", "account_id", "api_key"))


def not_configured(action) -> dict:
    return {
        "ok": False,
        "configured": False,
        "action": action,
        "detail": (
            "External e-sign is not connected. Set ESIGN_API_BASE, ESIGN_ACCOUNT_ID "
            "and ESIGN_API_KEY to enable it; offers use built-in click-to-sign "
            "until then."
        ),
    }


def create_envelope(offer, pdf_bytes=None) -> dict:
    """Push ``offer`` to the external provider for signature."""
    if not configured():
        return not_configured("create_envelope")
    raise NotImplementedError(  # pragma: no cover - requires live credentials
        "Connect a real e-sign provider client here."
    )


def envelope_status(envelope_id) -> dict:
    if not configured():
        return not_configured("envelope_status")
    raise NotImplementedError(  # pragma: no cover - requires live credentials
        "Connect a real e-sign provider client here."
    )
