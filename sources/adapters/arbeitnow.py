"""Arbeitnow's free job-board API (Europe-heavy, plenty of remote roles)."""

from sources.adapters.base import Adapter, RawItem, parse_dt, snippet_of
from sources.http import get_json

ENDPOINT = "https://www.arbeitnow.com/api/job-board-api"


class ArbeitnowAdapter(Adapter):
    slug = "arbeitnow"
    name = "Arbeitnow"
    kind = "API"

    def fetch(self, source):
        return self.parse(get_json(source.config.get("url") or ENDPOINT))

    def parse(self, payload):
        for job in payload.get("data") or []:
            yield RawItem(
                external_id=str(job.get("slug") or ""),
                title=job.get("title") or "",
                url=job.get("url") or "",
                company_name=job.get("company_name") or "",
                snippet=snippet_of(job.get("description")),
                location=job.get("location") or "",
                remote=bool(job.get("remote")),
                tags=[str(t).lower() for t in (job.get("tags") or [])],
                posted_at=parse_dt(job.get("created_at")),
            )
