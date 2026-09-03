"""Indeed XML feed for every published careers site's OPEN jobs."""

from xml.etree.ElementTree import Element, SubElement, tostring

from django.urls import reverse
from django.utils import timezone

from careers.gateway import absolute, site_url
from careers.models import CareersSite
from careers.seo import split_location
from jobs.models import Job


def _text(parent, tag, value):
    node = SubElement(parent, tag)
    node.text = value or ""
    return node


def indeed_feed_xml():
    """Indeed's required source/job envelope as a bytes payload."""
    root = Element("source")
    _text(root, "publisher", "Interview Portal")
    _text(root, "publisherurl", site_url())
    _text(root, "lastBuildDate", timezone.now().strftime("%a, %d %b %Y %H:%M:%S %z") or "")

    sites = CareersSite.objects.filter(published=True).select_related("company")
    for site in sites:
        jobs = (
            Job.objects.filter(company=site.company, status=Job.OPEN)
            .prefetch_related("skills")
            .order_by("-created_at")
        )
        for job in jobs:
            city, region, country = split_location(job.location)
            node = SubElement(root, "job")
            _text(node, "title", job.title)
            _text(node, "date", job.created_at.strftime("%a, %d %b %Y %H:%M:%S %z"))
            _text(node, "referencenumber", f"{site.slug}-{job.pk}")
            _text(node, "url", absolute(reverse("careers:job_detail", args=[site.slug, job.pk])))
            _text(node, "company", site.company.name)
            _text(node, "city", city)
            _text(node, "state", region)
            _text(node, "country", country)
            _text(node, "jobtype", job.get_employment_type_display().lower())
            description = job.description or ""
            if job.requirements:
                description = f"{description}\n\nRequirements:\n{job.requirements}"
            _text(node, "description", description)
    body = tostring(root, encoding="unicode")
    return f'<?xml version="1.0" encoding="utf-8"?>\n{body}'.encode()
