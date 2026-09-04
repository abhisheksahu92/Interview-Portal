"""The invitations table on the members page is the shared access-links
component (core/_access_links_table.html) — the same one clients/ uses."""

from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from core.models import Company, Invitation, Membership, User

pytestmark = pytest.mark.django_db


@pytest.fixture
def company(db):
    return Company.objects.create(name="Acme Staffing")


@pytest.fixture
def owner(company):
    user = User.objects.create_user(email="owner@acme.test", password="pw12345678")
    Membership.objects.create(user=user, company=company, role=Membership.OWNER)
    return user


@pytest.fixture
def recruiter(company):
    """A non-owner who may see the members page but not manage invitations."""
    user = User.objects.create_user(email="rec@acme.test", password="pw12345678")
    Membership.objects.create(user=user, company=company, role=Membership.RECRUITER)
    return user


@pytest.fixture
def invitation(company, owner):
    return Invitation.objects.create(
        company=company,
        email="waiting@acme.test",
        role=Membership.INTERVIEWER,
        invited_by=owner,
    )


def test_members_page_uses_the_shared_table(client, owner, invitation):
    client.force_login(owner)
    body = client.get(reverse("web:settings_members")).content.decode()
    assert "ip-access-links" in body
    assert "waiting@acme.test" in body
    assert "Interviewer" in body  # link_purpose column
    assert "Active" in body  # status badge
    assert "Last used" in body
    assert reverse("web:invite_resend", args=[invitation.pk]) in body
    assert reverse("web:invite_revoke", args=[invitation.pk]) in body
    assert "confirm(" in body


def test_expired_invitation_shows_the_expired_badge(client, owner, invitation):
    invitation.expires_at = timezone.now() - timedelta(days=1)
    invitation.save()
    client.force_login(owner)
    body = client.get(reverse("web:settings_members")).content.decode()
    assert "Expired" in body


def test_non_owner_sees_the_table_without_action_buttons(
    client, recruiter, invitation
):
    client.force_login(recruiter)
    body = client.get(reverse("web:settings_members")).content.decode()
    assert "ip-access-links" in body
    assert "waiting@acme.test" in body
    assert reverse("web:invite_revoke", args=[invitation.pk]) not in body
