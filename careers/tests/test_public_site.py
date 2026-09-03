import json
from xml.etree import ElementTree

import pytest
from django.db import transaction
from django.db.utils import IntegrityError
from django.urls import reverse

from careers.models import CareersSite, JobDistribution
from jobs.models import Job


def test_slug_defaults_from_company_slug(company):
    site = CareersSite.objects.create(company=company)
    assert site.slug == company.slug


def test_public_site_renders_branding_and_jobs(client, site, job):
    response = client.get(reverse("careers:site", args=[site.slug]))
    assert response.status_code == 200
    body = response.content.decode()
    assert "Build hiring with us" in body
    assert job.title in body
    assert "#123456" in body
    assert "ip-sidebar" not in body  # standalone shell, no app chrome


def test_unpublished_site_is_404(client, site):
    site.published = False
    site.save()
    assert client.get(reverse("careers:site", args=[site.slug])).status_code == 404


def test_unknown_slug_is_404(client, db):
    assert client.get(reverse("careers:site", args=["nope"])).status_code == 404


def test_custom_domain_resolution_via_host_header(client, site, job, settings):
    site.custom_domain = "Careers.Example.COM"
    site.save()
    assert site.custom_domain == "careers.example.com"
    settings.ALLOWED_HOSTS = ["careers.example.com", "testserver"]
    response = client.get(reverse("careers:index"), HTTP_HOST="careers.example.com")
    assert response.status_code == 200
    assert job.title in response.content.decode()


def test_custom_domain_ignored_when_unpublished(client, site, settings):
    site.custom_domain = "careers.example.com"
    site.published = False
    site.save()
    settings.ALLOWED_HOSTS = ["careers.example.com", "testserver"]
    response = client.get(reverse("careers:index"), HTTP_HOST="careers.example.com")
    assert response.status_code in {302, 403}  # falls through to the gated settings page


def test_blank_custom_domains_do_not_collide(company, site):
    from core.models import Company

    other = CareersSite.objects.create(company=Company.objects.create(name="Second Co"))
    assert site.custom_domain is None
    assert other.custom_domain is None


def test_filter_by_location(client, site, job, company):
    Job.objects.create(company=company, title="Remote SRE", location="Remote", status=Job.OPEN)
    response = client.get(reverse("careers:site", args=[site.slug]), {"location": "Pune"})
    body = response.content.decode()
    assert job.title in body
    assert "Remote SRE" not in body


def test_filter_by_skill_and_title(client, site, job, company):
    Job.objects.create(company=company, title="Designer", location="Pune", status=Job.OPEN)
    body = client.get(reverse("careers:site", args=[site.slug]), {"q": "Python"}).content.decode()
    assert job.title in body and "Designer" not in body
    body = client.get(reverse("careers:site", args=[site.slug]), {"q": "Design"}).content.decode()
    assert "Designer" in body


def test_draft_jobs_are_hidden(client, site, company):
    Job.objects.create(company=company, title="Secret Role", status=Job.DRAFT)
    body = client.get(reverse("careers:site", args=[site.slug])).content.decode()
    assert "Secret Role" not in body


def test_job_detail_has_json_ld_and_og_tags(client, site, job):
    response = client.get(reverse("careers:job_detail", args=[site.slug, job.pk]))
    assert response.status_code == 200
    body = response.content.decode()
    assert 'property="og:title"' in body
    raw = body.split('type="application/ld+json">')[1].split("</script>")[0]
    data = json.loads(raw)
    assert data["@type"] == "JobPosting"
    assert data["@context"] == "https://schema.org"
    assert data["title"] == job.title
    assert data["hiringOrganization"]["name"] == job.company.name
    assert data["jobLocation"]["address"]["addressLocality"] == "Pune"
    assert data["employmentType"] == "FULL_TIME"
    assert data["datePosted"]


def test_job_detail_links_to_web_apply_flow(client, site, job):
    body = client.get(
        reverse("careers:job_detail", args=[site.slug, job.pk])
    ).content.decode()
    assert reverse("web:job_public_detail", args=[job.pk]) in body


def test_job_detail_404_for_other_company_job(client, site, db):
    from core.models import Company

    other = Company.objects.create(name="Rival Inc")
    stray = Job.objects.create(company=other, title="Rival Role", status=Job.OPEN)
    assert (
        client.get(reverse("careers:job_detail", args=[site.slug, stray.pk])).status_code == 404
    )


def test_sitemap_lists_site_and_jobs(client, site, job):
    response = client.get(reverse("careers:sitemap", args=[site.slug]))
    assert response.status_code == 200
    assert response["Content-Type"].startswith("application/xml")
    root = ElementTree.fromstring(response.content)
    locs = [n.text for n in root.iter("{http://www.sitemaps.org/schemas/sitemap/0.9}loc")]
    assert any(loc.endswith(f"/careers/{site.slug}/") for loc in locs)
    assert any(loc.endswith(f"/jobs/{job.pk}/") for loc in locs)


def test_indeed_feed_is_well_formed_with_required_fields(client, site, job):
    response = client.get(reverse("careers:indeed_feed"))
    assert response.status_code == 200
    root = ElementTree.fromstring(response.content)
    assert root.tag == "source"
    assert root.find("publisher") is not None
    nodes = root.findall("job")
    assert len(nodes) == 1
    node = nodes[0]
    for tag in ("title", "date", "referencenumber", "url", "company", "city", "country",
                "jobtype", "description"):
        assert node.find(tag) is not None, tag
    assert node.find("title").text == job.title
    assert node.find("city").text == "Pune"


def test_indeed_feed_skips_unpublished_sites(client, site, job):
    site.published = False
    site.save()
    root = ElementTree.fromstring(client.get(reverse("careers:indeed_feed")).content)
    assert root.findall("job") == []


def test_about_text_is_xss_safe(client, site):
    site.about = '<script>alert("x")</script>\n\n- <img src=x onerror=alert(1)>'
    site.save()
    body = client.get(reverse("careers:site", args=[site.slug])).content.decode()
    assert "<script>alert" not in body
    assert "&lt;script&gt;" in body
    assert "<img" not in body.split("</header>")[1]
    assert "&lt;img src=x onerror=alert(1)&gt;" in body  # inert, escaped text
    assert "<li>" in body  # structure still rendered


def test_about_text_renders_paragraphs_and_lists(site):
    from careers.text import render_about

    html = render_about("Hello\n\n- one\n- two")
    assert html == "<p>Hello</p><ul><li>one</li><li>two</li></ul>"


@pytest.mark.django_db
def test_distribution_unique_per_board(job):
    JobDistribution.objects.create(job=job, board=JobDistribution.INDEED)
    with pytest.raises(IntegrityError), transaction.atomic():
        JobDistribution.objects.create(job=job, board=JobDistribution.INDEED)
