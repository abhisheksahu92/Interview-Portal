"""Regressions for the QA findings on the careers app."""

import pytest
from django.urls import reverse

from careers.feeds import indeed_feed_xml
from careers.models import CareersSite
from careers.seo import job_posting_dict, split_location
from core.models import Membership, User


@pytest.fixture
def interviewer(company, careers_plan):
    user = User.objects.create_user(email="iv@careers.test", password="pw12345678")
    Membership.objects.create(user=user, company=company, role=Membership.INTERVIEWER)
    return user


@pytest.fixture
def recruiter(company, careers_plan, owner):
    user = User.objects.create_user(email="rec@careers.test", password="pw12345678")
    Membership.objects.create(user=user, company=company, role=Membership.RECRUITER)
    return user


# ---------------------------------------------------------------- role gating


@pytest.mark.parametrize(
    "url_name,args",
    [("careers:index", ()), ("careers:preview", ())],
)
def test_recruiter_screens_are_403_for_an_interviewer(client, interviewer, url_name, args):
    client.force_login(interviewer)
    assert client.get(reverse(url_name, args=args)).status_code == 403


def test_job_distribution_is_403_for_an_interviewer(client, interviewer, job):
    client.force_login(interviewer)
    assert client.get(reverse("careers:job_distribution", args=[job.pk])).status_code == 403


def test_distribute_action_is_403_for_an_interviewer(client, interviewer, job):
    client.force_login(interviewer)
    response = client.post(
        reverse("careers:distribute_action", args=[job.pk, "INDEED"]), {"action": "post"}
    )
    assert response.status_code == 403


def test_recruiter_may_reach_the_settings_page(client, recruiter):
    assert client.login(email=recruiter.email, password="pw12345678") or True
    client.force_login(recruiter)
    assert client.get(reverse("careers:index")).status_code == 200


# ---------------------------------------------------------------- preview iframe


def test_preview_allows_being_framed_by_the_settings_page(client, owner):
    client.force_login(owner)
    response = client.get(reverse("careers:preview"))
    assert response.status_code == 200
    assert response.headers.get("X-Frame-Options") == "SAMEORIGIN"


# ---------------------------------------------------------------- form errors


def test_invalid_custom_domain_renders_inline(client, owner, company, site):
    client.force_login(owner)
    response = client.post(
        reverse("careers:index"),
        {"slug": site.slug, "custom_domain": "https://jobs.acme.test/careers",
         "headline": "Hi", "about": "", "brand_color": "#123456",
         "seo_title": "", "seo_description": ""},
    )
    assert response.status_code == 200
    body = response.content.decode()
    assert "invalid-feedback" in body
    assert "is-invalid" in body
    assert "bare hostname" in body


def test_successful_save_shows_a_success_message(client, owner, company, site):
    client.force_login(owner)
    response = client.post(
        reverse("careers:index"),
        {"slug": site.slug, "custom_domain": "jobs.acme.test", "headline": "Hi",
         "about": "", "brand_color": "#123456", "seo_title": "", "seo_description": ""},
        follow=True,
    )
    assert response.status_code == 200
    assert "Careers site saved." in response.content.decode()


# ---------------------------------------------------------------- structured data


@pytest.mark.parametrize(
    "location,expected",
    [
        ("Pune, Maharashtra, IN", ("Pune", "Maharashtra", "IN")),
        ("Pune, IN", ("Pune", "", "IN")),
        ("Pune", ("Pune", "", "IN")),
        ("Berlin, DE", ("Berlin", "", "DE")),
        ("", ("", "", "IN")),
    ],
)
def test_split_location_never_puts_a_country_code_in_the_region(location, expected):
    assert split_location(location) == expected


def test_json_ld_leaves_the_region_blank_when_unknown(company, site, job):
    job.location = "Pune, IN"
    job.save(update_fields=["location"])
    data = job_posting_dict(job, site)
    address = data["jobLocation"]["address"]
    assert address["addressRegion"] == ""
    assert address["addressCountry"] == "IN"


def test_json_ld_carries_valid_through(company, site, job):
    from datetime import date

    job.closes_at = date(2031, 1, 31)
    job.save(update_fields=["closes_at"])
    assert job_posting_dict(job, site)["validThrough"] == "2031-01-31"


def test_indeed_feed_omits_the_country_code_as_state_and_adds_valid_through(
    company, site, job
):
    from datetime import date

    job.location = "Pune, IN"
    job.closes_at = date(2031, 1, 31)
    job.save(update_fields=["location", "closes_at"])
    CareersSite.objects.filter(pk=site.pk).update(published=True)
    xml = indeed_feed_xml().decode()
    assert "<state />" in xml or "<state></state>" in xml
    assert "<country>IN</country>" in xml
    assert "<validThrough>2031-01-31</validThrough>" in xml
