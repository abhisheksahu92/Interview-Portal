"""Jira Cloud REST API integration for filing bugs and tracking hiring milestones."""

import base64
import json
import logging
from urllib.error import HTTPError
import urllib.request

from django.conf import settings

logger = logging.getLogger(__name__)


def create_jira_issue(
    summary: str,
    description: str,
    issue_type_name: str = "Task",
    project_key: str = "KAN",
) -> dict | None:
    """Create an issue in Jira Cloud via REST API v3 using Atlassian Document Format (ADF).

    Args:
        summary: Title/Summary of the issue.
        description: Plain text or multi-line details.
        issue_type_name: 'Task', 'Story', 'Subtask', or 'Epic' (default 'Task').
        project_key: Target project key (default 'KAN').

    Returns:
        dict with {'key': issue_key, 'id': issue_id} on success, None on error.
    """
    jira_url = getattr(settings, "JIRA_URL", "").rstrip("/")
    email = getattr(settings, "JIRA_EMAIL", "")
    token = getattr(settings, "JIRA_TOKEN", "")

    if not (jira_url and email and token):
        logger.debug("Jira credentials not configured; skipping issue creation.")
        return None

    auth_str = f"{email}:{token}".encode("utf-8")
    auth_header = "Basic " + base64.b64encode(auth_str).decode("utf-8")

    paragraphs = []
    for line in description.strip().split("\n"):
        line_clean = line.strip()
        if not line_clean:
            continue
        paragraphs.append({
            "type": "paragraph",
            "content": [{"type": "text", "text": line_clean}],
        })
    if not paragraphs:
        paragraphs = [{
            "type": "paragraph",
            "content": [{"type": "text", "text": "No details provided."}],
        }]

    payload = {
        "fields": {
            "project": {"key": project_key},
            "summary": summary[:255],
            "description": {
                "type": "doc",
                "version": 1,
                "content": paragraphs,
            },
            "issuetype": {"name": issue_type_name},
        }
    }

    endpoint = f"{jira_url}/rest/api/3/issue"
    req = urllib.request.Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": auth_header,
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            logger.info("Created Jira issue %s in project %s", data.get("key"), project_key)
            return {"key": data.get("key"), "id": data.get("id")}
    except HTTPError as exc:
        err_body = exc.read().decode("utf-8", errors="replace")
        logger.error("Jira HTTP error %s: %s", exc.code, err_body)
        return None
    except Exception as exc:
        logger.exception("Failed to create Jira issue: %s", exc)
        return None


def file_system_error_issue(path: str, user_str: str, error_details: str = "") -> dict | None:
    """Create a bug/task in Jira for an unhandled 500 server error."""
    summary = f"[Bug] 500 Internal Error on {path[:60]}"
    description = (
        f"Path: {path}\n"
        f"User: {user_str}\n"
        f"Details: {error_details or 'Internal server exception raised during request cycle.'}"
    )
    return create_jira_issue(summary, description, issue_type_name="Task", project_key="KAN")


def file_hiring_milestone_issue(milestone: str, candidate_name: str, job_title: str, company_name: str) -> dict | None:
    """Create a task in Jira when an application reaches Offer Accepted or Candidate Hired."""
    summary = f"[{milestone}] {candidate_name} — {job_title} ({company_name})"
    description = (
        f"Milestone: {milestone}\n"
        f"Candidate: {candidate_name}\n"
        f"Job Title: {job_title}\n"
        f"Company: {company_name}\n"
        f"Status: Workflow Action Complete"
    )
    return create_jira_issue(summary, description, issue_type_name="Task", project_key="KAN")
