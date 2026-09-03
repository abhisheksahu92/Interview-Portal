"""robots.txt and the root sitemap.xml."""

import pytest
from django.urls import reverse


@pytest.mark.django_db
def test_robots_allows_everything_and_points_at_the_sitemap(client):
    response = client.get("/robots.txt")
    assert response.status_code == 200
    assert response["Content-Type"].startswith("text/plain")
    body = response.content.decode()
    assert "User-agent: *" in body
    assert "Allow: /" in body
    assert "Disallow: /" not in body
    assert "Sitemap: http://testserver/sitemap.xml" in body


@pytest.mark.django_db
def test_sitemap_lists_the_landing_page(client):
    response = client.get("/sitemap.xml")
    assert response.status_code == 200
    assert response["Content-Type"].startswith("application/xml")
    body = response.content.decode()
    assert body.startswith("<?xml")
    assert "<urlset" in body
    assert "<loc>http://testserver/</loc>" in body


@pytest.mark.django_db
def test_sitemap_indexes_published_careers_sitemaps(client):
    from careers.models import CareersSite
    from core.models import Company

    company = Company.objects.create(name="Acme Staffing")
    site = CareersSite.objects.create(company=company, published=True)
    hidden = CareersSite.objects.create(
        company=Company.objects.create(name="Quiet Co"), published=False
    )

    body = client.get("/sitemap.xml").content.decode()
    assert reverse("careers:sitemap", args=[site.slug]) in body
    assert reverse("careers:site", args=[site.slug]) in body
    assert hidden.slug not in body
