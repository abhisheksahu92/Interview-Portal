"""JobPosting JSON-LD for board pages.

The payload is careers' builder verbatim — one schema, one place to fix it —
with the canonical url and directApply swapped for the board's own listing.
"""

import json

from django.urls import reverse

from careers.gateway import absolute
from careers.seo import job_posting_dict


def board_job_posting_dict(job, site):
    data = job_posting_dict(job, site)
    data["url"] = absolute(reverse("board:job_detail", args=[job.pk]))
    if not job.location:
        # No address to publish: Google requires jobLocationType instead.
        data.pop("jobLocation", None)
        data["jobLocationType"] = "TELECOMMUTE"
    return data


def board_job_posting_json(job, site):
    return json.dumps(board_job_posting_dict(job, site))
