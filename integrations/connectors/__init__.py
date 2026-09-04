"""Third-party connector adapters (HRMS + background check).

Each adapter is a small class over a :class:`integrations.models.ConnectorConfig`
row implementing the base contract in :mod:`integrations.connectors.base`:

* ``configured()`` — are the credentials this adapter needs present?
* ``push_hire(application)`` — HRMS: create an employee record for a new hire.
* ``start_check(candidate)`` — background check: kick off a screening.
* ``test_connection()`` — a cheap "are these credentials plausible" probe.

No adapter performs I/O unless it is configured, and every HTTP call routes
through ``base.Connector.request`` so tests can patch one seam and never touch
the network.
"""

from integrations.connectors.background_check import BackgroundCheckConnector
from integrations.connectors.base import (
    Connector,
    ConnectorResult,
    NotConfigured,
)
from integrations.connectors.greythr import GreytHRConnector
from integrations.connectors.keka import KekaConnector
from integrations.connectors.zoho_people import ZohoPeopleConnector

__all__ = [
    "ADAPTERS",
    "BackgroundCheckConnector",
    "Connector",
    "ConnectorResult",
    "GreytHRConnector",
    "KekaConnector",
    "NotConfigured",
    "ZohoPeopleConnector",
    "adapter_for",
    "adapter_class",
]

#: connector kind -> adapter class.
ADAPTERS = {
    cls.kind: cls
    for cls in (
        KekaConnector,
        ZohoPeopleConnector,
        GreytHRConnector,
        BackgroundCheckConnector,
    )
}


def adapter_class(kind):
    return ADAPTERS.get(kind)


def adapter_for(config):
    """The adapter wrapping ``config``, or None for an unknown kind."""
    cls = ADAPTERS.get(config.kind)
    return cls(config) if cls else None
