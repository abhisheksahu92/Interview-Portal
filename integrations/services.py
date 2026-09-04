"""Connector orchestration: what happens to third-party systems on a hire."""

import logging

from integrations.connectors.base import ConnectorResult
from integrations.models import ConnectorConfig

logger = logging.getLogger(__name__)


def push_hire_to_hrms(application):
    """Send ``application`` to every active HRMS connector for its company.

    Returns the list of :class:`~integrations.models.ConnectorRun` rows created.
    Each connector is isolated: one vendor being down does not stop the next,
    and nothing raises back into the hiring flow.
    """
    company = getattr(application, "company", None)
    if company is None:
        return []

    runs = []
    configs = ConnectorConfig.objects.for_company(company).active().hrms()
    for config in configs:
        adapter = config.adapter()
        if adapter is None:
            continue
        try:
            result = adapter.push_hire(application)
        except Exception as exc:
            logger.exception("integrations: %s push_hire failed", config.kind)
            result = ConnectorResult.error(f"{type(exc).__name__}: {exc}")
        runs.append(
            config.log(result.status, result.detail, application_id=application.pk)
        )
    return runs


def start_background_check(candidate, company):
    """Kick off a background check via the company's active BGV connector."""
    config = (
        ConnectorConfig.objects.for_company(company)
        .active()
        .filter(kind=ConnectorConfig.BACKGROUND_CHECK)
        .first()
    )
    if config is None:
        return None
    adapter = config.adapter()
    try:
        result = adapter.start_check(candidate)
    except Exception as exc:
        logger.exception("integrations: background check failed")
        result = ConnectorResult.error(f"{type(exc).__name__}: {exc}")
    return config.log(result.status, result.detail, candidate_id=getattr(candidate, "pk", None))


def probe_connection(config):
    """Probe ``config``'s credentials, logging the outcome."""
    adapter = config.adapter()
    if adapter is None:
        return ConnectorResult.error(f"No adapter for {config.kind}")
    try:
        result = adapter.test_connection()
    except Exception as exc:
        logger.exception("integrations: %s test_connection failed", config.kind)
        result = ConnectorResult.error(f"{type(exc).__name__}: {exc}")
    config.log(result.status, result.detail)
    return result
