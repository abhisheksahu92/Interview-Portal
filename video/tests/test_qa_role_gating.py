"""Recruiter video screens are owner/recruiter only — interviewers get a 403."""

import pytest
from django.urls import reverse

from core.models import Membership, User


@pytest.fixture
def interviewer(company, video_plan):
    user = User.objects.create_user(email="iv@acme.test", password="pw12345678")
    Membership.objects.create(user=user, company=company, role=Membership.INTERVIEWER)
    return user


@pytest.fixture
def as_interviewer(client, interviewer):
    client.force_login(interviewer)
    return client


def test_index_is_403(as_interviewer):
    assert as_interviewer.get(reverse("video:index")).status_code == 403


def test_question_library_is_403(as_interviewer):
    assert as_interviewer.get(reverse("video:question_list")).status_code == 403


def test_job_screens_are_403(as_interviewer, job):
    assert as_interviewer.get(reverse("video:job_screens", args=[job.pk])).status_code == 403


def test_invite_list_is_403(as_interviewer):
    assert as_interviewer.get(reverse("video:invite_list")).status_code == 403


def test_invite_review_is_403(as_interviewer, invite):
    assert as_interviewer.get(reverse("video:invite_review", args=[invite.pk])).status_code == 403


def test_owner_still_reaches_the_index(client, owner, video_plan):
    client.force_login(owner)
    assert client.get(reverse("video:index")).status_code == 200
