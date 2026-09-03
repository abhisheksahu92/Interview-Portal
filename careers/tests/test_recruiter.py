import pytest
from django.urls import reverse

from careers.models import CareersSite, JobDistribution


def test_settings_page_requires_login(client, db):
    response = client.get(reverse("careers:index"))
    assert response.status_code == 302
    assert "/accounts/login" in response["Location"]


def test_settings_page_gated_by_feature(client, free_owner):
    client.force_login(free_owner)
    assert client.get(reverse("careers:index")).status_code == 403


def test_settings_page_renders_and_autocreates_site(client, owner, company):
    client.force_login(owner)
    response = client.get(reverse("careers:index"))
    assert response.status_code == 200
    body = response.content.decode()
    assert "Careers site" in body
    assert "ALLOWED_HOSTS" in body
    assert "/careers/preview/" in body
    assert CareersSite.objects.filter(company=company).exists()


def test_publish_toggle(client, owner, company):
    client.force_login(owner)
    url = reverse("careers:index")
    client.get(url)
    site = CareersSite.objects.get(company=company)
    assert site.published is False
    client.post(url, {"publish": "1"})
    site.refresh_from_db()
    assert site.published is True
    client.post(url, {"publish": "1"})
    site.refresh_from_db()
    assert site.published is False


def test_site_editor_saves_fields(client, owner, company, site):
    client.force_login(owner)
    response = client.post(
        reverse("careers:index"),
        {
            "slug": site.slug,
            "custom_domain": " Jobs.Acme.Test ",
            "headline": "Come build",
            "about": "Nice place",
            "brand_color": "#ff0000",
            "seo_title": "Acme jobs",
            "seo_description": "Roles at Acme",
        },
        follow=True,
    )
    assert response.status_code == 200
    site.refresh_from_db()
    assert site.custom_domain == "jobs.acme.test"
    assert site.headline == "Come build"
    assert site.brand_color == "#ff0000"


def test_custom_domain_rejects_url(client, owner, site):
    client.force_login(owner)
    client.post(
        reverse("careers:index"),
        {"slug": site.slug, "custom_domain": "https://acme.test/careers", "brand_color": "#000000"},
    )
    site.refresh_from_db()
    assert site.custom_domain is None


def test_preview_renders_unpublished_site(client, owner, company):
    client.force_login(owner)
    response = client.get(reverse("careers:preview"))
    assert response.status_code == 200
    assert b"Preview" in response.content


@pytest.mark.parametrize("view", ["careers:preview"])
def test_preview_gated(client, free_owner, view):
    client.force_login(free_owner)
    assert client.get(reverse(view)).status_code == 403


def test_distribution_panel_lists_boards(client, owner, job, site):
    client.force_login(owner)
    response = client.get(reverse("careers:job_distribution", args=[job.pk]))
    assert response.status_code == 200
    body = response.content.decode()
    for label in ("Indeed", "Google for Jobs", "LinkedIn", "Naukri"):
        assert label in body
    assert "Connect account" in body  # LinkedIn/Naukri unconfigured
    assert "Copy posting text" in body
    assert job.title in body


def test_distribute_action_marks_feed_board_posted(client, owner, job, site):
    client.force_login(owner)
    response = client.post(
        reverse("careers:distribute_action", args=[job.pk, JobDistribution.INDEED])
    )
    assert response.status_code == 200
    distribution = JobDistribution.objects.get(job=job, board=JobDistribution.INDEED)
    assert distribution.status == JobDistribution.POSTED
    assert distribution.posted_at is not None


def test_distribute_action_fails_for_unconnected_board(client, owner, job, site, monkeypatch):
    monkeypatch.delenv("LINKEDIN_JOBS_TOKEN", raising=False)
    client.force_login(owner)
    client.post(reverse("careers:distribute_action", args=[job.pk, JobDistribution.LINKEDIN]))
    distribution = JobDistribution.objects.get(job=job, board=JobDistribution.LINKEDIN)
    assert distribution.status == JobDistribution.FAILED
    assert "not connected" in distribution.last_error.lower()


def test_distribute_action_posts_when_connected(client, owner, job, site, monkeypatch):
    monkeypatch.setenv("LINKEDIN_JOBS_TOKEN", "token-123")
    client.force_login(owner)
    client.post(reverse("careers:distribute_action", args=[job.pk, JobDistribution.LINKEDIN]))
    distribution = JobDistribution.objects.get(job=job, board=JobDistribution.LINKEDIN)
    assert distribution.status == JobDistribution.POSTED


def test_distribution_rejects_other_company_job(client, owner, db):
    from core.models import Company
    from jobs.models import Job

    stray = Job.objects.create(company=Company.objects.create(name="Rival"), title="X")
    client.force_login(owner)
    assert client.get(reverse("careers:job_distribution", args=[stray.pk])).status_code == 404


def test_gateway_reports_not_configured_by_default(monkeypatch):
    monkeypatch.delenv("LINKEDIN_JOBS_TOKEN", raising=False)
    monkeypatch.delenv("NAUKRI_API_KEY", raising=False)
    from careers.gateway import configured

    assert configured() is False


def test_posting_text_includes_link_and_details(job, site):
    from careers.gateway import posting_text

    text = posting_text(job, site)
    assert job.title in text
    assert "Python" in text
    assert f"/careers/{site.slug}/jobs/{job.pk}/" in text
