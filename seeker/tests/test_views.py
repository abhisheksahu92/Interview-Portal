"""Portal pages: candidates only, bulk apply is idempotent, mailbox stays private."""

import pytest
from django.urls import reverse

from core.models import Company, Membership, User
from jobs.models import Application
from seeker.models import SavedItem

pytestmark = pytest.mark.django_db


def test_pages_require_a_candidate_account(client):
    member = User.objects.create_user(email="rec@acme.test", password="pw12345678")
    Membership.objects.create(
        user=member, company=Company.objects.create(name="Acme"), role=Membership.RECRUITER
    )
    client.force_login(member)
    assert client.get(reverse("seeker:feed")).status_code == 403


def test_feed_renders_for_a_candidate(client, seeker_user, seeker):
    client.force_login(seeker_user)
    response = client.get(reverse("seeker:feed"))
    assert response.status_code == 200
    assert b"Find work" in response.content


def test_saving_a_job_then_bulk_apply_creates_one_application(client, seeker_user, seeker, job):
    client.force_login(seeker_user)
    client.post(reverse("seeker:save", args=["job", job.pk]))
    item = SavedItem.objects.get(seeker=seeker, job=job)
    for _ in range(2):
        client.post(reverse("seeker:bulk"), {"action": "apply", "item": [item.pk]})
    assert Application.objects.filter(job=job, candidate__user=seeker_user).count() == 1
    item.refresh_from_db()
    assert item.status == SavedItem.APPLIED


def test_open_and_track_marks_external_leads_applied(client, seeker_user, seeker, make_lead):
    item = SavedItem.objects.create(seeker=seeker, lead=make_lead())
    client.force_login(seeker_user)
    client.post(reverse("seeker:bulk"), {"action": "open", "item": [item.pk]})
    item.refresh_from_db()
    assert item.status == SavedItem.APPLIED


def test_mailbox_form_stores_the_password_encrypted(client, seeker_user, seeker):
    client.force_login(seeker_user)
    client.post(
        reverse("seeker:mailbox"),
        {
            "mailbox_email": "priya@example.test",
            "host": "smtp.example.test",
            "port": "587",
            "username": "priya",
            "password": "app-pw",
        },
    )
    seeker.refresh_from_db()
    assert seeker.mailbox_kind == seeker.SMTP
    assert "app-pw" not in seeker.mailbox_config
    assert seeker.get_mailbox_config()["password"] == "app-pw"
    # The page must never hand the secret back to the browser.
    assert b"app-pw" not in client.get(reverse("seeker:mailbox")).content


def test_a_blank_password_keeps_the_stored_one(client, seeker_user, seeker):
    client.force_login(seeker_user)
    payload = {
        "mailbox_email": "priya@example.test",
        "host": "smtp.example.test",
        "port": "587",
        "username": "priya",
    }
    client.post(reverse("seeker:mailbox"), {**payload, "password": "app-pw"})
    client.post(reverse("seeker:mailbox"), payload)
    seeker.refresh_from_db()
    assert seeker.get_mailbox_config()["password"] == "app-pw"


def test_add_lead_saves_a_pasted_posting(client, seeker_user, seeker):
    pytest.importorskip("sources.models")
    client.force_login(seeker_user)
    response = client.post(
        reverse("seeker:add_lead"),
        {
            "url": "https://linkedin.test/jobs/1",
            "title": "Django contractor",
            "company": "Zeta",
            "text": "Reach out to hiring@zeta.test about the Django contract role.",
        },
    )
    assert response.status_code == 302
    item = SavedItem.objects.get(seeker=seeker)
    assert item.lead.contact_email == "hiring@zeta.test"
    assert item.lead.source.slug == "manual"


def test_upgrade_records_intent_only(client, seeker_user, seeker):
    client.force_login(seeker_user)
    assert client.get(reverse("seeker:upgrade")).status_code == 200
    client.post(reverse("seeker:upgrade"))
    seeker.refresh_from_db()
    assert seeker.upgrade_requested_at is not None
    assert seeker.is_pro is False
