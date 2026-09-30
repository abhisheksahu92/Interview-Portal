"""Google Jules API client for autonomous background coding and maintenance agents."""

import hashlib
import json
import logging
import urllib.error
import urllib.request
from typing import Any

from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

JULES_API_BASE = "https://jules.googleapis.com/v1alpha"
DEFAULT_REPO_SOURCE = "sources/github/interviewportal02/interview-portal"
DEDUPE_CACHE_TTL = 3600  # 1 hour


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


def list_activities(session_id: str) -> list[dict[str, Any]]:
    """Retrieve all activities, progress updates, and artifacts of a session."""
    session_name = session_id if session_id.startswith("sessions/") else f"sessions/{session_id}"
    res = _request(f"{session_name}/activities")
    if res and "activities" in res:
        return res["activities"]
    return []


def create_session(
    prompt: str,
    repo_source: str = DEFAULT_REPO_SOURCE,
    title: str = "",
) -> dict[str, Any] | None:
    """Dispatch a new asynchronous task/session to Google Jules."""
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


# ---------------------------------------------------------------------------
# Automated Bug-Fixing Pipeline & Slack Dispatch
# ---------------------------------------------------------------------------


def dispatch_bug_fix_task(
    title: str,
    error_summary: str,
    traceback_str: str = "",
    path: str = "",
    dedupe_key: str = "",
) -> dict[str, Any] | None:
    """Trigger an autonomous Jules session to fix an unhandled error, if not duplicate."""
    if not is_configured():
        return None

    # Deduplicate against repeated errors within 1 hour
    sig = dedupe_key or f"{path}:{error_summary}"
    cache_key = f"jules_dedupe:{hashlib.sha256(sig.encode()).hexdigest()}"
    if cache.get(cache_key):
        logger.info("Jules task already dispatched for %s within 1h; skipping dedupe.", sig)
        return None
    cache.set(cache_key, 1, DEDUPE_CACHE_TTL)

    prompt = (
        f"# 🚨 Production Error Remediation Task\n\n"
        f"**Error Summary:** {error_summary}\n"
        f"**Endpoint/Path:** `{path}`\n\n"
        f"### Stack Trace:\n```\n{traceback_str[:3000]}\n```\n\n"
        f"### Mandatory Rules (Ponytail Ladder & GSD):\n"
        f"1. **Root cause fix, not symptom patching**: Fix the root cause in the shared function, not just a defensive guard at the symptom site.\n"
        f"2. **Shortest working diff**: YAGNI, reuse existing helpers in the codebase, no unnecessary abstractions.\n"
        f"3. **Verification**: Run `pytest` on affected test modules and ensure zero regressions.\n"
        f"4. **Commit & PR**: Commit with descriptive message and open a clean PR.\n"
    )

    clean_title = f"Fix: {title[:80]}"
    session = create_session(prompt=prompt, title=clean_title)
    if not session or "name" not in session:
        logger.warning("Failed to create Jules session for bug: %s", clean_title)
        return None

    session_id = session["name"]
    web_url = session.get("url") or f"https://jules.google.com/session/{session_id.split('/')[-1]}"

    # Send initial Slack dispatch notification
    try:
        from core.slack import send_slack_message
        send_slack_message(
            "system_errors",
            f":robot_face: *Jules AI Agent Dispatched to Fix Bug*\n"
            f"• *Issue*: `{clean_title}`\n"
            f"• *Path*: `{path}`\n"
            f"• *Jules Session*: <{web_url}|View Live Progress>",
        )
    except Exception:
        pass

    # Enqueue background polling task on worker
    try:
        from core.queue import enqueue
        enqueue("core.jules.poll_jules_session", session_id=session_id, error_title=clean_title, poll_count=0)
    except Exception as exc:
        logger.warning("Could not enqueue Jules poller to Redis: %s", exc)

    return session


def poll_jules_session(session_id: str, error_title: str, poll_count: int = 0) -> None:
    """Background task executed on worker to monitor Jules progress and notify Slack."""
    activities = list_activities(session_id)
    web_url = f"https://jules.google.com/session/{session_id.split('/')[-1]}"

    completed_activity = None
    question_activity = None

    for act in activities:
        if "sessionCompleted" in act or act.get("originator") == "agent" and "sessionCompleted" in act:
            completed_activity = act
            break
        # Detect agent question / prompt requiring human input
        if "question" in act or "userInterventionRequired" in act:
            question_activity = act

    if completed_activity:
        # Check artifacts for patch or PR details
        artifacts = completed_activity.get("artifacts", [])
        commit_msg = "Automated bugfix applied"
        for art in artifacts:
            git_patch = art.get("changeSet", {}).get("gitPatch", {})
            if "suggestedCommitMessage" in git_patch:
                commit_msg = git_patch["suggestedCommitMessage"].split("\n")[0]
                break

        try:
            from core.slack import send_slack_message
            send_slack_message(
                "system_errors",
                f":tada: *Jules AI Completed Fix for*: `{error_title}`\n"
                f"• *Commit*: {commit_msg}\n"
                f"• *Session Link*: <{web_url}|Review & Merge PR>\n"
                f"• *Status*: Fix ready for human review.",
            )
        except Exception:
            pass
        return

    if question_activity:
        try:
            from core.slack import send_slack_message
            send_slack_message(
                "system_errors",
                f":question: *Jules AI Needs Clarification on*: `{error_title}`\n"
                f"• *Session*: <{web_url}|Reply to Jules Agent>",
            )
        except Exception:
            pass
        return

    # If still in progress and under max polling limit (e.g. 20 iterations * 30s = 10 mins)
    if poll_count < 20:
        try:
            from core.queue import enqueue
            enqueue(
                "core.jules.poll_jules_session",
                session_id=session_id,
                error_title=error_title,
                poll_count=poll_count + 1,
                countdown=30,
            )
        except Exception:
            pass
