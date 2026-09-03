from datetime import timedelta

import pytest
from django.db import IntegrityError
from django.utils import timezone

from clients.models import Client, ClientAccess, Submission, generate_token

pytestmark = pytest.mark.django_db


def test_generate_token_is_unique_and_long():
    tokens = {generate_token() for _ in range(50)}
    assert len(tokens) == 50
    assert all(len(t) >= 32 for t in tokens)


def test_client_name_unique_per_company(company, other_company, make_client_row):
    make_client_row(company, "Initech")
    # same name in a different tenant is fine
    make_client_row(other_company, "Initech")
    with pytest.raises(IntegrityError):
        Client.objects.create(company=company, name="Initech")


def test_access_expiry_and_revoke(client_row):
    access = ClientAccess.objects.create(
        client=client_row,
        email="a@initech.test",
        expires_at=timezone.now() + timedelta(days=1),
    )
    assert access.is_active
    access.expires_at = timezone.now() - timedelta(days=1)
    assert access.is_expired and not access.is_active
    access.expires_at = None
    access.revoke()
    assert not access.is_active


def test_access_rotate_issues_new_token(access):
    old = access.token
    access.revoke()
    access.rotate(days=7)
    assert access.token != old
    assert access.is_active


def test_submission_unique_per_application_and_client(application, client_row):
    Submission.objects.create(application=application, client=client_row)
    with pytest.raises(IntegrityError):
        Submission.objects.create(application=application, client=client_row)


def test_record_client_decision_stamps_timeline(submission):
    assert not submission.is_decided
    assert len(submission.timeline()) == 1
    submission.record_client_decision(Submission.SHORTLISTED, "Looks good", 4)
    submission.refresh_from_db()
    assert submission.status == Submission.SHORTLISTED
    assert submission.decided_at is not None
    assert submission.client_rating == 4
    events = submission.timeline()
    assert len(events) == 2 and events[1]["rating"] == 4
