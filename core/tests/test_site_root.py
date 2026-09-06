"""robots.txt, the sitemap index, and the page sitemap it points at."""

import pytest
from django.urls import reverse


@pytest.mark.django_db
def test_robots_keeps_crawlers_out_of_the_signed_in_app(client):
    response = client.get("/robots.txt")

    assert response.status_code == 200
    assert response["Content-Type"].startswith("text/plain")
    body = response.content.decode()
    assert "User-agent: *" in body
    # The public surface stays crawlable...
    assert "Allow: /" in body
    assert "Sitemap: http://testserver/sitemap.xml" in body
    # ...while the workspace, the API and tokenised links do not.
    for path in ("/portal/", "/workspace/", "/billing/", "/api/", "/admin/", "/offers/"):
        assert f"Disallow: {path}" in body


@pytest.mark.django_db
def test_robots_does_not_block_the_public_pages(client):
    body = client.get("/robots.txt").content.decode()

    for path in ("/careers/", "/jobs/board/", "/accounts/"):
        assert f"Disallow: {path}" not in body


@pytest.mark.django_db
def test_root_sitemap_is_an_index_of_child_sitemaps(client):
    """A ``urlset`` here would tell crawlers each child sitemap is a page."""
    response = client.get("/sitemap.xml")

    assert response.status_code == 200
    assert response["Content-Type"].startswith("application/xml")
    body = response.content.decode()
    assert body.startswith("<?xml")
    assert "<sitemapindex" in body
    assert "<urlset" not in body
    assert "<loc>http://testserver/sitemap-pages.xml</loc>" in body


@pytest.mark.django_db
def test_root_sitemap_announces_the_job_board(client):
    """The board's job pages are the site's only real organic surface."""
    body = client.get("/sitemap.xml").content.decode()

    assert reverse("board:sitemap") in body


@pytest.mark.django_db
def test_page_sitemap_lists_the_landing_page_and_the_board(client):
    body = client.get("/sitemap-pages.xml").content.decode()

    assert "<urlset" in body
    assert "<loc>http://testserver/</loc>" in body
    assert reverse("board:list") in body


@pytest.mark.django_db
def test_published_careers_sites_appear_and_unpublished_ones_do_not(client):
    from careers.models import CareersSite
    from core.models import Company

    company = Company.objects.create(name="Acme Staffing")
    site = CareersSite.objects.create(company=company, published=True)
    hidden = CareersSite.objects.create(
        company=Company.objects.create(name="Quiet Co"), published=False
    )

    index = client.get("/sitemap.xml").content.decode()
    pages = client.get("/sitemap-pages.xml").content.decode()

    assert reverse("careers:sitemap", args=[site.slug]) in index
    assert reverse("careers:site", args=[site.slug]) in pages
    assert hidden.slug not in index
    assert hidden.slug not in pages
