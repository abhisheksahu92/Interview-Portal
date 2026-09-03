"""Structured data helpers: JobPosting JSON-LD (Google for Jobs) and locations."""

import json

from django.urls import reverse
from django.utils.html import escape

from careers.gateway import absolute

EMPLOYMENT_TYPE_MAP = {
    "FULL_TIME": "FULL_TIME",
    "CONTRACT": "CONTRACTOR",
    "INTERN": "INTERN",
}


def split_location(location):
    """Best-effort ``"Pune, Maharashtra, IN"`` -> (city, region, country)."""
    parts = [p.strip() for p in (location or "").split(",") if p.strip()]
    city = parts[0] if parts else ""
    region = parts[1] if len(parts) > 1 else ""
    country = parts[2] if len(parts) > 2 else "IN"
    return city, region, country


def job_posting_dict(job, site):
    """The JobPosting payload Google for Jobs expects."""
    city, region, country = split_location(job.location)
    url = absolute(reverse("careers:job_detail", args=[site.slug, job.pk]))
    description = job.description or ""
    if job.requirements:
        description = f"{description}\n\nRequirements:\n{job.requirements}"
    data = {
        "@context": "https://schema.org",
        "@type": "JobPosting",
        "title": job.title,
        "description": f"<p>{escape(description).replace(chr(10), '<br>')}</p>",
        "identifier": {
            "@type": "PropertyValue",
            "name": job.company.name,
            "value": str(job.pk),
        },
        "datePosted": job.created_at.date().isoformat(),
        "employmentType": EMPLOYMENT_TYPE_MAP.get(job.employment_type, "OTHER"),
        "hiringOrganization": {
            "@type": "Organization",
            "name": job.company.name,
            "sameAs": absolute(reverse("careers:site", args=[site.slug])),
        },
        "jobLocation": {
            "@type": "Place",
            "address": {
                "@type": "PostalAddress",
                "addressLocality": city,
                "addressRegion": region,
                "addressCountry": country,
            },
        },
        "directApply": True,
        "url": url,
    }
    if job.closes_at:
        data["validThrough"] = job.closes_at.isoformat()
    skills = ", ".join(s.name for s in job.skills.all())
    if skills:
        data["skills"] = skills
    return data


def job_posting_json(job, site):
    return json.dumps(job_posting_dict(job, site), indent=None, sort_keys=False)
