"""Remotive's public remote-jobs API. Everything on it is remote by definition."""

from sources.adapters.base import Adapter, RawItem, parse_dt, snippet_of
from sources.http import get_json

ENDPOINT = "https://remotive.com/api/remote-jobs?limit=100"


class RemotiveAdapter(Adapter):
    slug = "remotive"
    name = "Remotive"
    kind = "API"

    def fetch(self, source):
        return self.parse(get_json(source.config.get("url") or ENDPOINT))

    def parse(self, payload):
        for job in payload.get("jobs") or []:
            yield RawItem(
                external_id=str(job.get("id") or ""),
                title=job.get("title") or "",
                url=job.get("url") or "",
                company_name=job.get("company_name") or "",
                snippet=snippet_of(job.get("description")),
                location=job.get("candidate_required_location") or "",
                remote=True,
                budget_text=(job.get("salary") or "").strip()[:120],
                tags=[str(t).lower() for t in (job.get("tags") or [])],
                posted_at=parse_dt(job.get("publication_date")),
            )
