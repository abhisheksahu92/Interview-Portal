"""Adzuna's search API — the one aggregator with good India coverage.

Skipped cleanly when ``ADZUNA_APP_ID``/``ADZUNA_APP_KEY`` are unset.
"""

import urllib.parse

from django.conf import settings

from sources.adapters.base import Adapter, RawItem, looks_remote, parse_dt, snippet_of
from sources.http import get_json

ENDPOINT = "https://api.adzuna.com/v1/api/jobs/{country}/search/1?{query}"


def credentials():
    return (
        (getattr(settings, "ADZUNA_APP_ID", "") or "").strip(),
        (getattr(settings, "ADZUNA_APP_KEY", "") or "").strip(),
    )


class AdzunaAdapter(Adapter):
    slug = "adzuna"
    name = "Adzuna"
    kind = "API"

    def available(self):
        return all(credentials())

    def fetch(self, source):
        app_id, app_key = credentials()
        country = source.config.get("country") or "in"
        query = urllib.parse.urlencode(
            {
                "app_id": app_id,
                "app_key": app_key,
                "results_per_page": 50,
                "what": source.config.get("what") or "software developer",
                "content-type": "application/json",
            }
        )
        return self.parse(get_json(ENDPOINT.format(country=country, query=query)))

    def parse(self, payload):
        for job in payload.get("results") or []:
            location = (job.get("location") or {}).get("display_name") or ""
            yield RawItem(
                external_id=str(job.get("id") or ""),
                title=job.get("title") or "",
                url=job.get("redirect_url") or "",
                company_name=(job.get("company") or {}).get("display_name") or "",
                snippet=snippet_of(job.get("description")),
                location=location,
                remote=looks_remote(location, job.get("title")),
                salary_min=job.get("salary_min") or None,
                salary_max=job.get("salary_max") or None,
                currency="INR",
                tags=[str((job.get("category") or {}).get("label", "")).lower()],
                posted_at=parse_dt(job.get("created")),
            )
