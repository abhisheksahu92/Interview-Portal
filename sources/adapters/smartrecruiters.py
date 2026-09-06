"""SmartRecruiters public postings API.

The list endpoint carries no description, only metadata — good enough for a
lead, and it saves one request per posting.
"""

from sources.adapters.base import Adapter, RawItem, parse_dt, snippet_of
from sources.http import get_json

ENDPOINT = "https://api.smartrecruiters.com/v1/companies/{slug}/postings?limit=100"


class SmartRecruitersAdapter(Adapter):
    slug = "smartrecruiters"
    name = "SmartRecruiters"
    kind = "ATS"

    def fetch(self, source):
        board = source.config.get("slug") or ""
        return self.parse(get_json(ENDPOINT.format(slug=board)), board=board)

    def parse(self, payload, *, board=""):
        for job in payload.get("content") or []:
            location = job.get("location") or {}
            company = (job.get("company") or {}).get("name") or board
            place = location.get("fullLocation") or ", ".join(
                str(location.get(k)) for k in ("city", "country") if location.get(k)
            )
            yield RawItem(
                external_id=str(job.get("id") or ""),
                title=job.get("name") or "",
                # ``ref`` is the API URL; seekers need the public posting.
                url=f"https://jobs.smartrecruiters.com/{board}/{job.get('id', '')}",
                company_name=company,
                snippet=snippet_of(job.get("name")),
                location=place,
                remote=bool(location.get("remote")),
                tags=[
                    str((job.get(k) or {}).get("label", "")).lower()
                    for k in ("department", "function", "industry")
                    if (job.get(k) or {}).get("label")
                ],
                posted_at=parse_dt(job.get("releasedDate")),
            )
