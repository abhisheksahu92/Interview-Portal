"""External-service adapter for the scheduling app.

Environment variables: GOOGLE_OAUTH_CLIENT_ID, GOOGLE_OAUTH_CLIENT_SECRET, MS_OAUTH_CLIENT_ID, MS_OAUTH_CLIENT_SECRET

``configured()`` returns False until the scheduling agent implements the adapter and
the required environment variables are set, so callers must degrade gracefully
and tests never touch the network.
"""


def configured() -> bool:
    """True when this gateway has everything it needs to call out."""
    return False
