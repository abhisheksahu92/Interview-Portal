from datetime import timedelta

import pytest
from django.core import mail
from django.urls import reverse
from django.utils import timezone

from core.emails import send_invitation
from core.models import Company, Invitation, Membership, User


@pytest.fixture
def company(db):
    return Company.objects.create(name="Acme Staffing")


@pytest.fixture
def owner(company):
    user = User.objects.create_user(email="owner@acme.test", password="pw12345678")
    Membership.objects.create(user=user, company=company, role=Membership.OWNER)
    return user


def make_invite(company, owner, email="new@acme.test", **kwargs):
    return Invitation.objects.create(
        company=company,
        email=email,
        role=kwargs.pop("role", Membership.RECRUITER),
        invited_by=owner,
        **kwargs,
    )


@pytest.mark.django_db
def test_invitation_defaults_and_token(company, owner):
    invite = make_invite(company, owner, email="New@Acme.test")
    assert invite.email == "new@acme.test"
    assert len(invite.token) > 20
    assert invite.is_pending
    delta = invite.expires_at - timezone.now()
    assert timedelta(days=6, hours=23) < delta <= timedelta(days=7)
    assert invite.accepted_at is None


@pytest.mark.django_db
def test_send_invitation_emails_the_link(company, owner, rf):
    invite = make_invite(company, owner)
    mail.outbox.clear()
    request = rf.get("/")
    assert send_invitation(invite, request) == 1
    message = mail.outbox[0]
    assert message.to == ["new@acme.test"]
    assert company.name in message.subject
    assert invite.token in message.body
    html = message.alternatives[0][0]
    assert invite.token in html


@pytest.mark.django_db
def test_logged_in_get_shows_a_confirm_page_and_does_not_mutate(client, company, owner):
    invite = make_invite(company, owner, role=Membership.INTERVIEWER)
    user = User.objects.create_user(email="new@acme.test", password="pw12345678")
    client.force_login(user)
    response = client.get(reverse("core:invite_accept", args=[invite.token]))
    assert response.status_code == 200
    body = response.content.decode()
    assert "Accept invitation" in body
    assert "Interviewer" in body
    invite.refresh_from_db()
    assert invite.accepted_at is None
    assert not Membership.objects.filter(user=user, company=company).exists()


@pytest.mark.django_db
def test_used_invite_page_renders_inside_the_shell(client, company, owner):
    """An owner of another workspace still gets the app shell + page header."""
    invite = make_invite(company, owner, accepted_at=timezone.now())
    response = client.get(reverse("core:invite_accept", args=[invite.token]))
    body = response.content.decode()
    assert response.status_code == 400
    assert "Invitation unavailable" in body  # page header
    assert "ip-page-head" in body


@pytest.mark.django_db
def test_logged_in_matching_user_accepts(client, company, owner):
    invite = make_invite(company, owner, role=Membership.INTERVIEWER)
    user = User.objects.create_user(email="new@acme.test", password="pw12345678")
    client.force_login(user)
    response = client.post(reverse("core:invite_accept", args=[invite.token]))
    assert response.status_code == 302
    assert response["Location"] == "/"
    membership = Membership.objects.get(user=user, company=company)
    assert membership.role == Membership.INTERVIEWER
    invite.refresh_from_db()
    assert invite.accepted_at is not None
    assert client.session["company_id"] == company.id
    user.refresh_from_db()
    assert user.last_company_id == company.id


@pytest.mark.django_db
def test_accept_via_signup(client, company, owner):
    invite = make_invite(company, owner)
    url = reverse("core:invite_accept", args=[invite.token])
    page = client.get(url)
    assert page.status_code == 200
    assert b"new@acme.test" in page.content
    response = client.post(
        url,
        {
            "email": "ignored@evil.test",
            "first_name": "New",
            "last_name": "Hire",
            "password1": "sup3rsecret!23",
            "password2": "sup3rsecret!23",
        },
    )
    assert response.status_code == 302
    user = User.objects.get(email="new@acme.test")
    assert not user.is_candidate
    assert Membership.objects.filter(user=user, company=company).exists()
    invite.refresh_from_db()
    assert invite.accepted_at is not None


@pytest.mark.django_db
def test_expired_token_shows_error(client, company, owner):
    invite = make_invite(
        company, owner, expires_at=timezone.now() - timedelta(days=1)
    )
    user = User.objects.create_user(email="new@acme.test", password="pw12345678")
    client.force_login(user)
    response = client.get(reverse("core:invite_accept", args=[invite.token]))
    assert response.status_code == 400
    assert b"expired" in response.content
    assert not Membership.objects.filter(user=user, company=company).exists()


@pytest.mark.django_db
def test_used_token_shows_error(client, company, owner):
    invite = make_invite(company, owner, accepted_at=timezone.now())
    response = client.get(reverse("core:invite_accept", args=[invite.token]))
    assert response.status_code == 400
    assert b"already been used" in response.content


@pytest.mark.django_db
def test_mixed_case_invite_email_still_matches(client, company, owner):
    invite = make_invite(company, owner, email="New.Hire@Acme.test")
    user = User.objects.create_user(email="NEW.hire@acme.TEST", password="pw12345678")
    client.force_login(user)
    response = client.post(reverse("core:invite_accept", args=[invite.token]))
    assert response.status_code == 302
    assert Membership.objects.filter(user=user, company=company).exists()


@pytest.mark.django_db
def test_wrong_email_logged_in_user_gets_error(client, company, owner):
    invite = make_invite(company, owner)
    other = User.objects.create_user(email="someone@else.test", password="pw12345678")
    client.force_login(other)
    response = client.get(reverse("core:invite_accept", args=[invite.token]))
    assert response.status_code == 400
    assert b"new@acme.test" in response.content
    assert not Membership.objects.filter(user=other, company=company).exists()


@pytest.mark.django_db
def test_unknown_token_is_404(client):
    assert client.get(reverse("core:invite_accept", args=["nope"])).status_code == 404
