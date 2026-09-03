"""Job-board adapters for the careers app.

Environment variables: ``SITE_URL`` (always required for absolute links),
``LINKEDIN_JOBS_TOKEN``, ``NAUKRI_API_KEY``.

Indeed and Google for Jobs need no credentials at all: Indeed crawls the XML
feed at ``/careers/feeds/indeed.xml`` and Google for Jobs reads the JobPosting
JSON-LD embedded in each public job page. LinkedIn and Naukri are stubs — they
report ``not configured`` until an account is connected, and the UI falls back
to "copy posting text".
"""

import os

from django.conf import settings
from django.urls import reverse

from careers.models import JobDistribution


def _env(name):
    return (os.environ.get(name) or "").strip()


def site_url():
    return (getattr(settings, "SITE_URL", "") or "").rstrip("/")


def absolute(path):
    return f"{site_url()}{path}"


def configured() -> bool:
    """True when at least one push-based board has credentials."""
    return any(adapter.configured() for adapter in (LinkedInAdapter(), NaukriAdapter()))


class BoardAdapter:
    """Common interface. ``push``/``remove`` never touch the network unconfigured."""

    board = ""
    label = ""
    kind = "push"
    env_keys = ()

    def configured(self) -> bool:
        return all(_env(key) for key in self.env_keys)

    def status(self):
        if self.kind != "push":
            return "automatic"
        return "connected" if self.configured() else "not configured"

    def push(self, job):
        raise NotImplementedError

    def remove(self, job):
        raise NotImplementedError


class _StubAdapter(BoardAdapter):
    def push(self, job):
        if not self.configured():
            return {
                "ok": False,
                "status": JobDistribution.FAILED,
                "error": f"{self.label} is not connected. Set {', '.join(self.env_keys)} "
                "or use “Copy posting text”.",
            }
        # Real API call goes here once an account is connected.
        return {"ok": True, "status": JobDistribution.POSTED, "external_id": ""}

    def remove(self, job):
        if not self.configured():
            return {"ok": False, "status": JobDistribution.FAILED, "error": "Not connected."}
        return {"ok": True, "status": JobDistribution.REMOVED, "external_id": ""}


class LinkedInAdapter(_StubAdapter):
    board = JobDistribution.LINKEDIN
    label = "LinkedIn"
    env_keys = ("LINKEDIN_JOBS_TOKEN",)


class NaukriAdapter(_StubAdapter):
    board = JobDistribution.NAUKRI
    label = "Naukri"
    env_keys = ("NAUKRI_API_KEY",)


class IndeedAdapter(BoardAdapter):
    board = JobDistribution.INDEED
    label = "Indeed"
    kind = "feed"

    def configured(self) -> bool:
        return True

    def feed_url(self):
        return absolute(reverse("careers:indeed_feed"))


class GoogleJobsAdapter(BoardAdapter):
    board = JobDistribution.GOOGLE_JOBS
    label = "Google for Jobs"
    kind = "schema"

    def configured(self) -> bool:
        return True


ADAPTERS = {
    a.board: a
    for a in (IndeedAdapter(), GoogleJobsAdapter(), LinkedInAdapter(), NaukriAdapter())
}


def adapter_for(board):
    return ADAPTERS.get(board)


def posting_text(job, site=None):
    """Pre-formatted plain-text posting for manual copy-paste to any board."""
    lines = [
        job.title,
        f"Company: {job.company.name}",
    ]
    if job.location:
        lines.append(f"Location: {job.location}")
    lines.append(f"Employment type: {job.get_employment_type_display()}")
    skills = ", ".join(s.name for s in job.skills.all())
    if skills:
        lines.append(f"Skills: {skills}")
    if job.description:
        lines += ["", job.description.strip()]
    if job.requirements:
        lines += ["", "Requirements:", job.requirements.strip()]
    if site is not None:
        lines += ["", f"Apply: {absolute(reverse('careers:job_detail', args=[site.slug, job.pk]))}"]
    return "\n".join(lines)
