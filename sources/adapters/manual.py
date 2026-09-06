"""Leads a person pasted in.

There is nothing to fetch — the row exists so the seeker app's "Add a lead"
page has a :class:`~sources.models.Source` to hang its leads off, and so those
leads take part in dedupe, tagging and expiry like every other lead.
"""

from sources.adapters.base import Adapter


class ManualAdapter(Adapter):
    slug = "manual"
    name = "Pasted by a person"
    kind = "API"

    def fetch(self, source):
        return []
