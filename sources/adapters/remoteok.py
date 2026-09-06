"""RemoteOK's public feed.

Two quirks drive this adapter: row 0 is a legal notice rather than a job, and
their terms require linking back to the RemoteOK URL — so we keep their ``url``
untouched instead of following it through to the company's own site.
"""

from sources.adapters.base import Adapter, RawItem, parse_dt, snippet_of
from sources.http import get_json

ENDPOINT = "https://remoteok.com/api"


class RemoteOkAdapter(Adapter):
    slug = "remoteok"
    name = "RemoteOK"
    kind = "API"

    def fetch(self, source):
        return self.parse(get_json(source.config.get("url") or ENDPOINT))

    def parse(self, payload):
        rows = payload if isinstance(payload, list) else []
        for job in rows:
            if not isinstance(job, dict) or job.get("legal") or not job.get("id"):
                continue  # row 0 is the licence notice
            yield RawItem(
                external_id=str(job.get("id")),
                title=job.get("position") or "",
                url=job.get("url") or f"https://remoteok.com/remote-jobs/{job.get('slug', '')}",
                company_name=job.get("company") or "",
                snippet=snippet_of(job.get("description")),
                location=job.get("location") or "Remote",
                remote=True,
                salary_min=job.get("salary_min") or None,
                salary_max=job.get("salary_max") or None,
                currency="USD" if job.get("salary_min") else "",
                tags=[str(t).lower() for t in (job.get("tags") or [])],
                posted_at=parse_dt(job.get("date") or job.get("epoch")),
            )
