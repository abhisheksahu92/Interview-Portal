"""The connector contract shared by every adapter."""

import logging
from dataclasses import dataclass, field

import requests

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 10


class NotConfigured(Exception):
    """Raised when an adapter is asked to act without credentials."""


@dataclass
class ConnectorResult:
    """The uniform return value of every adapter call.

    ``status`` mirrors :class:`integrations.models.ConnectorRun` statuses, so a
    result can be logged verbatim.
    """

    status: str
    detail: str = ""
    payload: dict = field(default_factory=dict)

    OK = "OK"
    SKIPPED = "SKIPPED"
    ERROR = "ERROR"

    @property
    def ok(self):
        return self.status == self.OK

    @classmethod
    def success(cls, detail="", **payload):
        return cls(cls.OK, detail, payload)

    @classmethod
    def skipped(cls, detail="not configured", **payload):
        return cls(cls.SKIPPED, detail, payload)

    @classmethod
    def error(cls, detail, **payload):
        return cls(cls.ERROR, detail, payload)


class Connector:
    """Base adapter: reads its credentials from a ConnectorConfig row."""

    #: matches a ``ConnectorConfig.kind`` value.
    kind = ""
    label = ""
    #: settings keys that must be non-empty for ``configured()`` to be True.
    required_settings: tuple = ()
    #: settings keys whose values are secrets (masked in the UI).
    secret_settings: tuple = ("api_key", "api_secret", "token")
    #: optional settings keys the form should still offer.
    optional_settings: tuple = ()

    def __init__(self, config):
        self.config = config

    def __repr__(self):  # pragma: no cover - debugging aid
        return f"<{type(self).__name__} configured={self.configured()}>"

    # --- credentials ------------------------------------------------------
    @property
    def settings(self) -> dict:
        return self.config.settings or {}

    @classmethod
    def setting_fields(cls):
        """Every settings key this adapter understands, in form order."""
        return tuple(cls.required_settings) + tuple(cls.optional_settings)

    def get(self, key, default=""):
        value = self.settings.get(key, default)
        return value.strip() if isinstance(value, str) else value

    def configured(self) -> bool:
        """True when every required setting is present and non-empty."""
        return all(self.get(key) for key in self.required_settings)

    def missing_settings(self):
        return [key for key in self.required_settings if not self.get(key)]

    # --- HTTP -------------------------------------------------------------
    def base_url(self):
        return self.get("base_url")

    def headers(self):
        token = self.get("api_key")
        return {"Authorization": f"Bearer {token}", "Accept": "application/json"}

    def request(self, method, path, json=None):
        """The single network seam; tests patch this (or ``requests``)."""
        url = path if path.startswith("http") else f"{self.base_url().rstrip('/')}{path}"
        return requests.request(
            method, url, json=json, headers=self.headers(), timeout=TIMEOUT_SECONDS
        )

    def _call(self, method, path, json=None, success="ok"):
        """``request`` plus uniform result/error handling."""
        try:
            response = self.request(method, path, json=json)
        except Exception as exc:
            logger.warning("%s: request failed: %s", self.kind, exc)
            return ConnectorResult.error(f"{type(exc).__name__}: {exc}")
        code = getattr(response, "status_code", None)
        if code is not None and 200 <= int(code) < 300:
            return ConnectorResult.success(success, response_code=int(code))
        return ConnectorResult.error(f"HTTP {code}", response_code=code)

    # --- capabilities -----------------------------------------------------
    def test_connection(self) -> ConnectorResult:
        if not self.configured():
            return ConnectorResult.skipped(
                "not configured: missing " + ", ".join(self.missing_settings())
            )
        return self._call("GET", self.probe_path, success="connection ok")

    probe_path = "/"

    def push_hire(self, application) -> ConnectorResult:
        """HRMS adapters override; non-HRMS adapters decline."""
        return ConnectorResult.skipped("this connector does not accept hires")

    def start_check(self, candidate) -> ConnectorResult:
        """Background-check adapters override; others decline."""
        return ConnectorResult.skipped("this connector does not run checks")


def employee_payload(application):
    """The vendor-neutral new-employee record built from an Application.

    HRMS adapters reshape this into their own field names; keeping the
    extraction in one place means a missing candidate profile or job cannot
    break three adapters in three different ways.
    """
    candidate = getattr(application, "candidate", None)
    user = getattr(candidate, "user", None)
    job = getattr(application, "job", None)
    offer = None
    manager = getattr(application, "offers", None)
    if manager is not None:
        offer = manager.order_by("-pk").first()

    first_name = getattr(user, "first_name", "") or ""
    last_name = getattr(user, "last_name", "") or ""
    return {
        "application_id": application.pk,
        "email": getattr(user, "email", "") or "",
        "first_name": first_name,
        "last_name": last_name,
        "full_name": (f"{first_name} {last_name}".strip() or getattr(user, "email", "")),
        "phone": getattr(candidate, "phone", "") or "",
        "job_title": getattr(job, "title", "") or "",
        "location": getattr(job, "location", "") or "",
        "employment_type": getattr(job, "employment_type", "") or "",
        "joining_date": (
            offer.joining_date.isoformat()
            if offer is not None and getattr(offer, "joining_date", None)
            else None
        ),
        "salary": (str(offer.salary) if offer is not None else None),
        "currency": (getattr(offer, "currency", None) if offer is not None else None),
    }
