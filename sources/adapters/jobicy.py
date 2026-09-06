"""Jobicy's remote-jobs API. camelCase field names, salaries when known."""

from sources.adapters.base import Adapter, RawItem, parse_dt, snippet_of
from sources.http import get_json

ENDPOINT = "https://jobicy.com/api/v2/remote-jobs?count=50"


class JobicyAdapter(Adapter):
    slug = "jobicy"
    name = "Jobicy"
    kind = "API"

    def fetch(self, source):
        return self.parse(get_json(source.config.get("url") or ENDPOINT))

    def parse(self, payload):
        for job in payload.get("jobs") or []:
            yield RawItem(
                external_id=str(job.get("id") or job.get("jobSlug") or ""),
                title=job.get("jobTitle") or "",
                url=job.get("url") or "",
                company_name=job.get("companyName") or "",
                snippet=snippet_of(job.get("jobExcerpt") or job.get("jobDescription")),
                location=job.get("jobGeo") or "",
                remote=True,
                salary_min=job.get("salaryMin") or None,
                salary_max=job.get("salaryMax") or None,
                currency=(job.get("salaryCurrency") or "").upper()[:8],
                tags=[str(t).lower() for t in (job.get("jobIndustry") or [])],
                posted_at=parse_dt(job.get("pubDate")),
            )
