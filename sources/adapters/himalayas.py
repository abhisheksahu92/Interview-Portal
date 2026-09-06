"""Himalayas' JSON jobs feed. ``guid`` is the canonical posting URL and id."""

from sources.adapters.base import Adapter, RawItem, parse_dt, snippet_of
from sources.http import get_json

ENDPOINT = "https://himalayas.app/jobs/api?limit=50"


class HimalayasAdapter(Adapter):
    slug = "himalayas"
    name = "Himalayas"
    kind = "API"

    def fetch(self, source):
        return self.parse(get_json(source.config.get("url") or ENDPOINT))

    def parse(self, payload):
        for job in payload.get("jobs") or []:
            guid = job.get("guid") or job.get("applicationLink") or ""
            locations = job.get("locationRestrictions") or []
            yield RawItem(
                external_id=str(guid),
                title=job.get("title") or "",
                url=guid,
                company_name=job.get("companyName") or "",
                snippet=snippet_of(job.get("excerpt") or job.get("description")),
                location=", ".join(str(x) for x in locations) or "Worldwide",
                remote=True,
                salary_min=job.get("minSalary") or None,
                salary_max=job.get("maxSalary") or None,
                currency=(job.get("currency") or "").upper()[:8],
                tags=[str(t).lower() for t in (job.get("categories") or [])],
                posted_at=parse_dt(job.get("pubDate")),
            )
