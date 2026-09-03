"""External-service adapter for the careers app.

Environment variables: SITE_URL

``configured()`` returns False until the careers agent implements the adapter and
the required environment variables are set, so callers must degrade gracefully
and tests never touch the network.
"""


def configured() -> bool:
    """True when this gateway has everything it needs to call out."""
    return False
