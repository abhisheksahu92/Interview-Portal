"""Google Jules API client for autonomous background coding and maintenance agents."""

import json
import logging
import urllib.error
import urllib.request
from typing import Any

from django.conf import settings

logger = logging.getLogger(__name__)

JULES_API_BASE = "https://jules.googleapis.com/v1alpha"


def _api_key() -> str:
    """Retrieve the Jules API key from settings or environment."""
    return getattr(settings, "JULES_KEY", "") or ""


def is_configured() -> bool:
    """Return True if JULES_KEY is present and ready to use."""
    return bool(_api_key().strip())


def _request(endpoint: str, data: dict[str, Any] | None = None, method: str = "GET") -> dict[str, Any] | None:
    """Execute an authenticated request against the Google Jules REST API."""
    key = _api_key().strip()
    if not key:
        logger.debug("Jules API key not configured; skipping request.")
        return None

    url = f"{JULES_API_BASE}/{endpoint.lstrip('/')}"
    headers = {
        "X-Goog-Api-Key": key,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    body = json.dumps(data).encode("utf-8") if data is not None else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            content = resp.read().decode("utf-8")
            return json.loads(content) if content else {}
    except urllib.error.HTTPError as exc:
        err_body = exc.read().decode("utf-8", errors="replace")
        logger.error("Jules API error HTTP %s on %s: %s", exc.code, endpoint, err_body[:300])
        return None
    except Exception as exc:
        logger.exception("Failed request to Jules API on %s: %s", endpoint, exc)
        return None


def list_sessions(page_size: int = 20) -> list[dict[str, Any]]:
    """List ongoing and completed Jules agent tasks/sessions."""
    res = _request(f"sessions?pageSize={page_size}")
    if res and "sessions" in res:
        return res["sessions"]
    return []


def get_session(session_id: str) -> dict[str, Any] | None:
    """Retrieve details and progress of a specific Jules session."""
    session_name = session_id if session_id.startswith("sessions/") else f"sessions/{session_id}"
    return _request(session_name)


def create_session(
    prompt: str,
    repo_source: str = "sources/github/interviewportal02/interview-portal",
    title: str = "",
) -> dict[str, Any] | None:
    """Dispatch a new asynchronous task/session to Google Jules.

    Args:
        prompt: Detailed task prompt / coding instruction.
        repo_source: Source repo identifier linked to Jules.
        title: Optional human-readable title.
    """
    payload: dict[str, Any] = {
        "prompt": prompt,
        "sourceContext": {
            "source": repo_source,
            "environmentVariablesEnabled": True,
        },
    }
    if title:
        payload["title"] = title

    return _request("sessions", data=payload, method="POST")
