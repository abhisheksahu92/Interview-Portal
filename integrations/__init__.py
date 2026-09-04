"""Integrations tier: outbound webhooks, HRMS/background-check connectors, API keys.

The two names other apps and tests reach for live here::

    from integrations import emit, verify_signature

``emit`` is the event-bus entrypoint (also called by this app's own signals);
``verify_signature`` is the helper a customer copies into their receiver to
check the ``X-IP-Signature`` header.
"""

from integrations.signing import build_signature, verify_signature

__all__ = ["build_signature", "emit", "verify_signature"]


def emit(company, event, payload):
    """Lazy re-export of :func:`integrations.events.emit` (avoids app-loading
    order problems when this package is imported from settings-time code)."""
    from integrations.events import emit as _emit

    return _emit(company, event, payload)
