"""The database refuses a saved row that is neither, or both, of its two targets."""

import pytest
from django.db import IntegrityError, transaction

from seeker.models import SavedItem

pytestmark = pytest.mark.django_db


def test_saved_item_needs_a_target(seeker):
    with pytest.raises(IntegrityError), transaction.atomic():
        SavedItem.objects.create(seeker=seeker)


def test_saved_item_cannot_hold_both(seeker, job, make_lead):
    lead = make_lead()
    with pytest.raises(IntegrityError), transaction.atomic():
        SavedItem.objects.create(seeker=seeker, job=job, lead=lead)


def test_saved_item_accepts_exactly_one(seeker, job):
    item = SavedItem.objects.create(seeker=seeker, job=job)
    assert item.title == "Backend Engineer"
    assert item.company_name == "Acme Staffing"


def test_mailbox_config_round_trips_encrypted(seeker):
    seeker.set_mailbox_config({"host": "smtp.test", "password": "hunter2"})
    seeker.save()
    seeker.refresh_from_db()
    # Stored as a Fernet token: the secret is not readable in the column.
    assert "hunter2" not in seeker.mailbox_config
    assert seeker.get_mailbox_config()["password"] == "hunter2"
