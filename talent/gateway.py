"""External-service adapter for the talent app.

Environment variables: (none yet)

``configured()`` returns False until the talent agent implements the adapter and
the required environment variables are set, so callers must degrade gracefully
and tests never touch the network.
"""


def configured() -> bool:
    """True when this gateway has everything it needs to call out."""
    return False
