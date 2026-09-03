"""Phase 3 wiring: what the sidebar, kanban cards, job screens and dashboard
show a paid tenant versus one whose trial has expired onto FREE.
"""

from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from web.tests.conftest import free_expired, paid

# --- sidebar --------------------------------------------------------------

# (feature, label) for every gated sidebar entry.
GATED_NAV = [
    ("scheduling", "Schedule"),
    ("video", "Video"),
    ("offers", "Offers"),
    ("careers_page", "Careers"),
    ("analytics", "Analytics"),
    ("client_portal", "Clients"),
]

# Reachable on every plan, so they carry no lock badge: Talent searches the
# company's own sourced pool, while the marketplace storefront and the branding
# page degrade in-page (pool search and the white-label form hide themselves).
UNGATED_NAV = ["talent:index", "marketplace:index", "partners:settings"]


def _locks(html):
    """The features whose sidebar item rendered a "Pro" lock badge."""
    return {
        feature
        for feature, _ in GATED_NAV
        if f'data-ip-lock="{feature}"' in html
    }


@pytest.mark.django_db
def test_agency_sidebar_has_no_locks_and_links_every_feature(client, owner, company):
    paid(company)
    client.force_login(owner)
    html = client.get(reverse("web:dashboard")).content.decode()
    assert _locks(html) == set()
    for url_name in [
        "scheduling:index",
        "video:index",
        "offers:index",
        "careers:index",
        "analytics:index",
        "clients:index",
        *UNGATED_NAV,
    ]:
        assert reverse(url_name) in html


@pytest.mark.django_db
def test_free_expired_sidebar_locks_every_paid_feature_but_keeps_it_visible(
    client, owner, company
):
    free_expired(company)
    client.force_login(owner)
    html = client.get(reverse("web:dashboard")).content.decode()
    assert _locks(html) == {feature for feature, _ in GATED_NAV}
    # Still an upsell, not a disappearance: every label is on the page and the
    # lock points at billing rather than at the gated app.
    for _, label in GATED_NAV:
        assert label in html
    assert reverse("billing:overview") in html
    assert reverse("scheduling:index") not in html


@pytest.mark.django_db
def test_pages_reachable_on_every_plan_are_linked_not_locked(client, owner, company):
    """A lock badge must never hide a page the tenant can actually open."""
    free_expired(company)
    client.force_login(owner)
    dashboard = client.get(reverse("web:dashboard")).content.decode()
    for url_name in UNGATED_NAV:
        assert reverse(url_name) in dashboard
        assert client.get(reverse(url_name)).status_code == 200
    assert 'data-ip-lock="marketplace"' not in dashboard
    assert 'data-ip-lock="white_label"' not in dashboard


@pytest.mark.django_db
def test_gated_page_returns_the_branded_403_for_a_free_company(
    client, owner, company
):
    free_expired(company)
    client.force_login(owner)
    response = client.get(reverse("analytics:index"))
    assert response.status_code == 403
    assert b"Interview" in response.content


# --- kanban card actions --------------------------------------------------


@pytest.mark.django_db
def test_card_dropdown_offers_every_paid_action(
    client, owner, company, make_job, make_application
):
    paid(company)
    job = make_job(company)
    application = make_application(job, "cand1@x.test")
    client.force_login(owner)
    html = client.get(reverse("web:job_detail", args=[job.pk])).content.decode()
    assert f"app-actions-{application.pk}" in html
    assert reverse("scheduling:application_schedule", args=[application.pk]) in html
    assert reverse("clients:submit_application", args=[application.pk]) in html
    assert reverse("offers:create", args=[application.pk]) in html


@pytest.mark.django_db
def test_card_dropdown_disappears_for_a_free_company(
    client, owner, company, make_job, make_application
):
    free_expired(company)
    job = make_job(company)
    application = make_application(job, "cand2@x.test")
    client.force_login(owner)
    html = client.get(reverse("web:job_detail", args=[job.pk])).content.decode()
    assert f"app-actions-{application.pk}" not in html
    assert reverse("offers:create", args=[application.pk]) not in html
    # The core advance/reject/review actions are untouched by the gating.
    assert reverse("web:application_advance", args=[application.pk]) in html
    assert reverse("web:application_review", args=[application.pk]) in html


@pytest.mark.django_db
def test_video_action_posts_to_an_active_screen_when_the_job_has_one(
    client, owner, company, make_job, make_application
):
    from video.models import VideoScreen

    paid(company)
    job = make_job(company)
    application = make_application(job, "cand3@x.test")
    screen = VideoScreen.objects.create(job=job, title="Screen", is_active=True)
    client.force_login(owner)
    html = client.get(reverse("web:job_detail", args=[job.pk])).content.decode()
    assert reverse("video:invite_create", args=[screen.pk, application.pk]) in html


@pytest.mark.django_db
def test_video_action_links_to_screen_setup_when_the_job_has_none(
    client, owner, company, make_job, make_application
):
    paid(company)
    job = make_job(company)
    make_application(job, "cand4@x.test")
    client.force_login(owner)
    html = client.get(reverse("web:job_detail", args=[job.pk])).content.decode()
    assert reverse("video:job_screens", args=[job.pk]) in html


@pytest.mark.django_db
def test_inactive_video_screens_are_ignored(
    client, owner, company, make_job, make_application
):
    from video.models import VideoScreen

    paid(company)
    job = make_job(company)
    application = make_application(job, "cand5@x.test")
    screen = VideoScreen.objects.create(job=job, title="Old", is_active=False)
    client.force_login(owner)
    html = client.get(reverse("web:job_detail", args=[job.pk])).content.decode()
    assert reverse("video:invite_create", args=[screen.pk, application.pk]) not in html
    assert reverse("video:job_screens", args=[job.pk]) in html


# --- upcoming interview on the card --------------------------------------


def _interview(company, application, **kwargs):
    from scheduling.models import Interview

    start = kwargs.pop("start", timezone.now() + timedelta(days=1))
    return Interview.objects.create(
        company=company,
        application=application,
        scheduled_start=start,
        scheduled_end=start + timedelta(hours=1),
        status=kwargs.pop("status", Interview.CONFIRMED),
        **kwargs,
    )


@pytest.mark.django_db
def test_card_shows_the_next_upcoming_interview(
    client, owner, company, make_job, make_application
):
    paid(company)
    job = make_job(company)
    application = make_application(job, "cand6@x.test")
    soonest = _interview(
        company, application, start=timezone.now() + timedelta(days=1)
    )
    _interview(company, application, start=timezone.now() + timedelta(days=9))
    client.force_login(owner)
    html = client.get(reverse("web:job_detail", args=[job.pk])).content.decode()
    assert soonest.scheduled_start.strftime("%H:%M") in html


@pytest.mark.django_db
def test_card_ignores_past_and_cancelled_interviews(
    client, owner, company, make_job, make_application
):
    from scheduling.models import Interview

    paid(company)
    job = make_job(company)
    application = make_application(job, "cand7@x.test")
    _interview(company, application, start=timezone.now() - timedelta(days=3))
    _interview(
        company,
        application,
        start=timezone.now() + timedelta(days=4),
        status=Interview.CANCELLED,
    )
    client.force_login(owner)
    html = client.get(reverse("web:job_detail", args=[job.pk])).content.decode()
    assert "bi-calendar2-check" not in html


@pytest.mark.django_db
def test_board_does_not_query_per_card_for_interviews(
    client, owner, company, make_job, make_application
):
    """The interviews prefetch keeps the board's query count flat."""
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    paid(company)
    job = make_job(company)
    for index in range(2):
        application = make_application(job, f"few{index}@x.test")
        _interview(company, application)
    client.force_login(owner)
    url = reverse("web:job_detail", args=[job.pk])

    def count():
        with CaptureQueriesContext(connection) as captured:
            assert client.get(url).status_code == 200
        return len(captured)

    count()  # warm plan/session lookups so only the board is measured
    baseline = count()
    for index in range(2, 8):
        application = make_application(job, f"many{index}@x.test")
        _interview(company, application)
    assert count() == baseline


# --- job detail action bar ------------------------------------------------


@pytest.mark.django_db
def test_job_action_bar_carries_every_paid_action(client, owner, company, make_job):
    paid(company)
    job = make_job(company)
    client.force_login(owner)
    html = client.get(reverse("web:job_detail", args=[job.pk])).content.decode()
    assert reverse("video:job_screens", args=[job.pk]) in html
    assert reverse("careers:job_distribution", args=[job.pk]) in html
    assert reverse("clients:job_client", args=[job.pk]) in html
    assert 'id="cx-dist-panel"' in html


@pytest.mark.django_db
def test_job_action_bar_hides_gated_actions_for_a_free_company(
    client, owner, company, make_job
):
    free_expired(company)
    job = make_job(company)
    client.force_login(owner)
    html = client.get(reverse("web:job_detail", args=[job.pk])).content.decode()
    assert reverse("video:job_screens", args=[job.pk]) not in html
    assert reverse("careers:job_distribution", args=[job.pk]) not in html
    assert reverse("clients:job_client", args=[job.pk]) not in html
    assert 'id="cx-dist-panel"' not in html
    # The always-on actions stay.
    assert reverse("web:job_edit", args=[job.pk]) in html


# --- job form: end client -------------------------------------------------


@pytest.mark.django_db
def test_job_form_shows_the_end_client_field_when_entitled(client, owner, company):
    paid(company)
    client.force_login(owner)
    html = client.get(reverse("web:job_create")).content.decode()
    assert "End client" in html
    assert 'name="client"' in html


@pytest.mark.django_db
def test_job_form_omits_the_end_client_field_for_a_free_company(
    client, owner, company
):
    free_expired(company)
    client.force_login(owner)
    html = client.get(reverse("web:job_create")).content.decode()
    assert 'name="client"' not in html


@pytest.mark.django_db
def test_creating_a_job_sets_its_end_client(client, owner, company):
    from clients.models import Client as EndClient
    from jobs.models import Job

    paid(company)
    end_client = EndClient.objects.create(company=company, name="Northwind")
    client.force_login(owner)
    response = client.post(
        reverse("web:job_create"),
        {
            "title": "Django Dev",
            "location": "Pune",
            "description": "d",
            "requirements": "r",
            "employment_type": Job.FULL_TIME,
            "status": Job.DRAFT,
            "client": end_client.pk,
        },
    )
    assert response.status_code == 302
    job = Job.objects.get(title="Django Dev")
    assert job.client_id == end_client.pk


@pytest.mark.django_db
def test_editing_a_job_can_change_and_clear_its_end_client(
    client, owner, company, make_job
):
    from clients.models import Client as EndClient
    from jobs.models import Job

    paid(company)
    end_client = EndClient.objects.create(company=company, name="Northwind")
    job = make_job(company, status=Job.DRAFT)
    client.force_login(owner)
    payload = {
        "title": job.title,
        "location": "",
        "description": "",
        "requirements": "",
        "employment_type": Job.FULL_TIME,
        "status": Job.DRAFT,
    }
    client.post(reverse("web:job_edit", args=[job.pk]), {**payload, "client": end_client.pk})
    job.refresh_from_db()
    assert job.client_id == end_client.pk

    client.post(reverse("web:job_edit", args=[job.pk]), {**payload, "client": ""})
    job.refresh_from_db()
    assert job.client_id is None


@pytest.mark.django_db
def test_a_job_cannot_be_pointed_at_another_companys_client(
    client, owner, company, other_company, make_job
):
    from clients.models import Client as EndClient
    from jobs.models import Job

    paid(company)
    foreign = EndClient.objects.create(company=other_company, name="Globex Inc")
    job = make_job(company, status=Job.DRAFT)
    client.force_login(owner)
    response = client.post(
        reverse("web:job_edit", args=[job.pk]),
        {
            "title": job.title,
            "location": "",
            "description": "",
            "requirements": "",
            "employment_type": Job.FULL_TIME,
            "status": Job.DRAFT,
            "client": foreign.pk,
        },
    )
    assert response.status_code == 200
    job.refresh_from_db()
    assert job.client_id is None


# --- candidate profile ----------------------------------------------------


@pytest.mark.django_db
def test_candidate_profile_offers_the_talent_pool_opt_in(client, candidate):
    client.force_login(candidate)
    html = client.get(reverse("web:candidate_profile")).content.decode()
    assert 'id="ip-pool-opt-in"' in html
    assert reverse("marketplace:pool_opt_in") in html
    # The partial's own usage example must not have become a live self-include.
    assert html.count('id="ip-pool-opt-in"') == 1


# --- dashboard cards ------------------------------------------------------


@pytest.mark.django_db
def test_dashboard_lists_upcoming_interviews_when_scheduling_is_enabled(
    client, owner, company, make_job, make_application
):
    paid(company)
    job = make_job(company)
    application = make_application(job, "dash1@x.test")
    interview = _interview(company, application)
    client.force_login(owner)
    html = client.get(reverse("web:dashboard")).content.decode()
    assert "Upcoming interviews" in html
    assert "dash1@x.test" in html
    assert interview.scheduled_start.strftime("%H:%M") in html


@pytest.mark.django_db
def test_dashboard_upcoming_card_shows_at_most_five(
    client, owner, company, make_job, make_application
):
    paid(company)
    job = make_job(company)
    for index in range(7):
        application = make_application(job, f"dash{index}@many.test")
        _interview(company, application, start=timezone.now() + timedelta(days=index + 1))
    client.force_login(owner)
    html = client.get(reverse("web:dashboard")).content.decode()
    assert html.count("bi-calendar2") >= 0
    assert sum(f"dash{i}@many.test" in html for i in range(7)) == 5


@pytest.mark.django_db
def test_dashboard_counts_pending_offers_when_offers_are_enabled(
    client, owner, company, make_job, make_application
):
    from offers.models import Offer, OfferTemplate

    paid(company)
    job = make_job(company)
    template = OfferTemplate.default_for(company)
    for index, status in enumerate([Offer.SENT, Offer.VIEWED, Offer.DRAFT, Offer.ACCEPTED]):
        application = make_application(job, f"offer{index}@x.test")
        Offer.objects.create(application=application, template=template, status=status)
    client.force_login(owner)
    html = client.get(reverse("web:dashboard")).content.decode()
    assert "Pending offers" in html
    assert reverse("offers:index") in html
    # Only SENT + VIEWED are still awaiting a signature.
    assert ">2<" in html


@pytest.mark.django_db
def test_dashboard_hides_both_cards_for_a_free_company(
    client, owner, company, make_job, make_application
):
    free_expired(company)
    job = make_job(company)
    application = make_application(job, "dashfree@x.test")
    _interview(company, application)
    client.force_login(owner)
    html = client.get(reverse("web:dashboard")).content.decode()
    assert "Upcoming interviews" not in html
    assert "Pending offers" not in html
    # The original KPI row is untouched.
    assert "Open jobs" in html
    assert "Avg fit score" in html


@pytest.mark.django_db
def test_dashboard_interviews_are_scoped_to_the_tenant(
    client, owner, company, other_company, make_job, make_application
):
    paid(company)
    paid(other_company)
    other_job = make_job(other_company, title="Their Job")
    other_application = make_application(other_job, "theirs@x.test")
    _interview(other_company, other_application)
    client.force_login(owner)
    html = client.get(reverse("web:dashboard")).content.decode()
    assert "theirs@x.test" not in html
