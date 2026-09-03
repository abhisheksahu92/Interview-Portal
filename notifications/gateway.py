"""External-service adapter for the notifications app.

Environment variables: WHATSAPP_TOKEN, WHATSAPP_PHONE_ID

``configured()`` returns False until the notifications agent implements the adapter and
the required environment variables are set, so callers must degrade gracefully
and tests never touch the network.
"""


def configured() -> bool:
    """True when this gateway has everything it needs to call out."""
    return False
