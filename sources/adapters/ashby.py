"""Ashby job-board API.

Some boards are enormous (12MB+), which :mod:`sources.http` caps; unlisted rows
are filtered here because Ashby returns drafts alongside live postings.
"""

from sources.adapters.base import Adapter, RawItem, looks_remote, parse_dt, snippet_of
from sources.http import get_json

ENDPOINT = "https://api.ashbyhq.com/posting-api/job-board/{slug}"


class AshbyAdapter(Adapter):
    slug = "ashby"
    name = "Ashby"
    kind = "ATS"

    def fetch(self, source):
        board = source.config.get("slug") or ""
        return self.parse(get_json(ENDPOINT.format(slug=board)), board=board)

    def parse(self, payload, *, board=""):
        for job in payload.get("jobs") or []:
            if job.get("isListed") is False:
                continue
            location = job.get("location") or ""
            yield RawItem(
                external_id=str(job.get("id") or ""),
                title=job.get("title") or "",
                url=job.get("jobUrl") or job.get("applyUrl") or "",
                company_name=board.title(),
                snippet=snippet_of(job.get("descriptionPlain") or job.get("descriptionHtml")),
                location=location,
                remote=bool(job.get("isRemote")) or looks_remote(location),
                tags=[str(v).lower() for v in (job.get("department"), job.get("team")) if v],
                posted_at=parse_dt(job.get("publishedAt")),
            )
