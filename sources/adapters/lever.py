"""Lever public postings API. Returns a bare JSON list, not an envelope."""

from sources.adapters.base import Adapter, RawItem, looks_remote, parse_dt, snippet_of
from sources.http import get_json

ENDPOINT = "https://api.lever.co/v0/postings/{slug}?mode=json"


class LeverAdapter(Adapter):
    slug = "lever"
    name = "Lever"
    kind = "ATS"

    def fetch(self, source):
        board = source.config.get("slug") or ""
        return self.parse(get_json(ENDPOINT.format(slug=board)), board=board)

    def parse(self, payload, *, board=""):
        for job in payload if isinstance(payload, list) else []:
            categories = job.get("categories") or {}
            location = categories.get("location") or ""
            yield RawItem(
                external_id=str(job.get("id") or ""),
                title=job.get("text") or "",
                url=job.get("hostedUrl") or job.get("applyUrl") or "",
                company_name=board.title(),
                snippet=snippet_of(job.get("descriptionPlain") or job.get("description")),
                location=location,
                remote=looks_remote(location, job.get("workplaceType")),
                tags=[
                    str(categories.get(key)).lower()
                    for key in ("team", "department", "commitment")
                    if categories.get(key)
                ],
                posted_at=parse_dt((job.get("createdAt") or 0) / 1000 or None),
            )
