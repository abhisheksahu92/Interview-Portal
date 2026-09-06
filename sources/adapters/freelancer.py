"""Freelancer.com's public active-projects API — the freelance/gig side.

Budgets come as a min/max plus a currency code (INR is common), which is the
only useful money signal on this feed, so it becomes ``budget_text``.
"""

from sources.adapters.base import Adapter, RawItem, parse_dt, snippet_of
from sources.http import get_json

ENDPOINT = (
    "https://www.freelancer.com/api/projects/0.1/projects/active/"
    "?limit=50&job_details=true&full_description=true"
)


def _budget_text(budget, code):
    low, high = (budget or {}).get("minimum"), (budget or {}).get("maximum")
    if low and high:
        return f"{code} {low:,.0f}-{high:,.0f}".strip()
    if low:
        return f"{code} {low:,.0f}+".strip()
    return ""


class FreelancerAdapter(Adapter):
    slug = "freelancer"
    name = "Freelancer.com"
    kind = "API"

    def fetch(self, source):
        return self.parse(get_json(source.config.get("url") or ENDPOINT))

    def parse(self, payload):
        for project in (payload.get("result") or {}).get("projects") or []:
            currency = (project.get("currency") or {}).get("code") or ""
            budget = project.get("budget") or {}
            yield RawItem(
                external_id=str(project.get("id") or ""),
                kind="FREELANCE",
                title=project.get("title") or "",
                url=f"https://www.freelancer.com/projects/{project.get('seo_url', '')}",
                snippet=snippet_of(
                    project.get("preview_description") or project.get("description")
                ),
                location=((project.get("location") or {}).get("country") or {}).get("name") or "",
                remote=True,
                salary_min=budget.get("minimum") or None,
                salary_max=budget.get("maximum") or None,
                currency=currency[:8],
                budget_text=_budget_text(budget, currency),
                tags=[str(j.get("name", "")).lower() for j in (project.get("jobs") or [])],
                posted_at=parse_dt(project.get("time_submitted") or project.get("submitdate")),
            )
