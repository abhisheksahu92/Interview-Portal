"""Greenhouse public board API. ``source.config["slug"]`` is the board name."""

from sources.adapters.base import Adapter, RawItem, looks_remote, parse_dt, snippet_of
from sources.http import get_json

ENDPOINT = "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true"


class GreenhouseAdapter(Adapter):
    slug = "greenhouse"
    name = "Greenhouse"
    kind = "ATS"

    def fetch(self, source):
        board = source.config.get("slug") or ""
        return self.parse(get_json(ENDPOINT.format(slug=board)), board=board)

    def parse(self, payload, *, board=""):
        for job in payload.get("jobs") or []:
            location = (job.get("location") or {}).get("name") or ""
            yield RawItem(
                external_id=str(job.get("id") or ""),
                title=job.get("title") or "",
                url=job.get("absolute_url") or "",
                company_name=job.get("company_name") or board.title(),
                snippet=snippet_of(job.get("content")),
                location=location,
                remote=looks_remote(location),
                tags=[str(d.get("name", "")).lower() for d in (job.get("departments") or [])],
                posted_at=parse_dt(job.get("first_published") or job.get("updated_at")),
            )
