"""External-service adapter for the marketplace app.

Environment variables: RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET

``configured()`` returns False until the marketplace agent implements the adapter and
the required environment variables are set, so callers must degrade gracefully
and tests never touch the network.
"""


def configured() -> bool:
    """True when this gateway has everything it needs to call out."""
    return False
