"""External-service adapter surface for the scheduling app.

Environment variables: ``GOOGLE_OAUTH_CLIENT_ID``, ``GOOGLE_OAUTH_CLIENT_SECRET``,
``MS_OAUTH_CLIENT_ID``, ``MS_OAUTH_CLIENT_SECRET``.

The real work lives in :mod:`scheduling.calendar`; this module is the small,
stable "is anything wired up?" seam the rest of the codebase and the UI use, so
callers degrade gracefully and tests never touch the network.
"""


def configured() -> bool:
    """True when at least one calendar provider has OAuth credentials."""
    from scheduling.calendar.base import adapters

    return any(cls.configured() for cls in adapters().values())


def status():
    """Per-provider ``{provider, label, configured, note}`` rows for the UI."""
    from scheduling.calendar.base import provider_status

    return provider_status()
