"""Tests for the shared secret-link plumbing in core/tokens.py."""

from datetime import timedelta

import pytest
from django.utils import timezone

from clients.models import Client, ClientAccess
from core.models import Company, Invitation, Membership, User
from core.tokens import (
    DEFAULT_TOKEN_BYTES,
    TokenState,
    default_expiry,
    generate_token,
    resolve_token,
    token_invalid_response,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def company(db):
    return Company.objects.create(name="Acme Staffing")


@pytest.fixture
def access(company):
    client_row = Client.objects.create(company=company, name="Initech")
    return ClientAccess.objects.create(client=client_row, email="hr@initech.test")


# --------------------------------------------------------------------------- #
# generators
# --------------------------------------------------------------------------- #


def test_generate_token_is_unique_and_url_safe():
    tokens = {generate_token() for _ in range(50)}
    assert len(tokens) == 50
    assert all(len(t) >= DEFAULT_TOKEN_BYTES for t in tokens)
    assert all(set(t) <= set(
        "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_"
    ) for t in tokens)


def test_generate_token_respects_nbytes():
    assert len(generate_token(8)) < len(generate_token(64))


def test_default_expiry_none_means_never():
    assert default_expiry(None) is None
    assert timedelta(days=6) < default_expiry(7) - timezone.now() <= timedelta(days=7)


# --------------------------------------------------------------------------- #
# TokenMixin state machine (exercised through a concrete adopter)
# --------------------------------------------------------------------------- #


def test_fresh_row_is_active(access):
    assert access.is_active
    assert not access.is_expired and not access.is_revoked
    assert access.token_state is TokenState.ACTIVE
    assert access.token_status_label == "Active"
    assert access.token_status_kind == "accent"


def test_expiry_flips_state(access):
    access.expires_at = timezone.now() - timedelta(seconds=1)
    assert access.is_expired and not access.is_active
    assert access.token_state is TokenState.EXPIRED
    assert access.token_status_kind == "danger"


def test_no_expiry_never_expires(access):
    access.expires_at = None
    assert not access.is_expired and access.is_active


def test_revoke_is_idempotent_and_wins_over_expiry(access):
    access.revoke()
    first = access.revoked_at
    assert first is not None and not access.is_active
    access.revoke()
    access.refresh_from_db()
    assert access.revoked_at == first
    access.expires_at = timezone.now() - timedelta(days=1)
    # revocation is reported first: it is the more deliberate state
    assert access.token_state is TokenState.REVOKED


def test_rotate_replaces_the_token_and_unrevokes(access):
    old = access.token
    access.revoke()
    access.rotate(days=3)
    access.refresh_from_db()
    assert access.token != old
    assert access.revoked_at is None
    assert access.is_active
    assert timedelta(days=2) < access.expires_at - timezone.now() <= timedelta(days=3)


def test_rotate_defaults_to_the_models_expiry_days(access):
    access.rotate()
    delta = access.expires_at - timezone.now()
    assert timedelta(days=ClientAccess.EXPIRY_DAYS - 1) < delta


def test_touch_records_last_used(access):
    assert access.last_used_at is None
    access.touch()
    access.refresh_from_db()
    assert access.last_used_at is not None


# --------------------------------------------------------------------------- #
# resolve_token
# --------------------------------------------------------------------------- #


def test_resolve_token_active(access):
    resolution = resolve_token(ClientAccess, access.token)
    assert resolution.ok and bool(resolution) is True
    assert resolution.obj == access
    assert resolution.state is TokenState.ACTIVE
    assert resolution.status_code == 200


def test_resolve_token_expired(access):
    access.expires_at = timezone.now() - timedelta(days=1)
    access.save()
    resolution = resolve_token(ClientAccess, access.token)
    assert not resolution.ok
    assert resolution.state is TokenState.EXPIRED
    assert resolution.status_code == 410
    assert "expired" in resolution.reason


def test_resolve_token_revoked(access):
    access.revoke()
    resolution = resolve_token(ClientAccess, access.token)
    assert resolution.state is TokenState.REVOKED
    assert resolution.status_code == 410


@pytest.mark.parametrize("token", ["not-a-real-token", "", None])
def test_resolve_token_unknown(access, token):
    resolution = resolve_token(ClientAccess, token)
    assert resolution.obj is None
    assert resolution.state is TokenState.UNKNOWN
    assert resolution.status_code == 404


def test_resolve_token_unpacks_as_a_pair(access):
    obj, state = resolve_token(ClientAccess, access.token)
    assert obj == access and state is TokenState.ACTIVE


def test_resolve_token_honours_a_narrowed_queryset(access, company):
    other = Company.objects.create(name="Other Inc")
    other_client = Client.objects.create(company=other, name="Elsewhere")
    scoped = ClientAccess.objects.filter(client=other_client)
    assert resolve_token(ClientAccess, access.token, queryset=scoped).state is (
        TokenState.UNKNOWN
    )


def test_resolve_token_select_related_still_finds_the_row(access):
    resolution = resolve_token(
        ClientAccess, access.token, select_related=("client__company",)
    )
    assert resolution.obj.client.company.name == "Acme Staffing"


# --------------------------------------------------------------------------- #
# token_invalid_response
# --------------------------------------------------------------------------- #


def test_token_invalid_response_uses_the_state_default_status(rf, access):
    access.revoke()
    response = token_invalid_response(rf.get("/"), resolve_token(ClientAccess, access.token))
    assert response.status_code == 410
    body = response.content.decode()
    assert "no longer valid" in body
    assert "revoked" in body


def test_token_invalid_response_status_can_be_overridden(rf):
    response = token_invalid_response(
        rf.get("/"), resolve_token(ClientAccess, "nope"), status=400
    )
    assert response.status_code == 400


def test_token_invalid_response_takes_a_bare_state(rf):
    response = token_invalid_response(rf.get("/"), TokenState.EXPIRED)
    assert response.status_code == 410
    assert "expired" in response.content.decode()


def test_token_invalid_response_renders_in_the_portal_shell(rf, access):
    response = token_invalid_response(
        rf.get("/"),
        TokenState.UNKNOWN,
        context={
            "base_template": "clients/portal/base.html",
            "brand_name": "Initech",
            "contact_hint": "Ring your recruiter.",
        },
    )
    body = response.content.decode()
    assert "Initech" in body
    assert "Ring your recruiter." in body
    assert "ip-shell" not in body  # no recruiter chrome


# --------------------------------------------------------------------------- #
# Invitation: the mixin plus its accepted_at semantics
# --------------------------------------------------------------------------- #


@pytest.fixture
def invitation(company):
    owner = User.objects.create_user(email="owner@acme.test", password="pw12345678")
    Membership.objects.create(user=owner, company=company, role=Membership.OWNER)
    return Invitation.objects.create(
        company=company, email="new@acme.test", invited_by=owner
    )


def test_invitation_uses_the_mixin_columns(invitation):
    assert invitation.revoked_at is None
    assert invitation.last_used_at is None
    assert invitation.expires_at is not None
    assert invitation.is_active and invitation.is_pending


def test_accepted_invitation_reads_as_spent(invitation):
    user = User.objects.create_user(email="new@acme.test", password="pw12345678")
    invitation.accept(user)
    assert invitation.is_accepted
    assert not invitation.is_pending
    assert invitation.token_state is TokenState.REVOKED
    assert invitation.token_status_label == "Accepted"


def test_revoking_an_invitation_ends_its_pending_state(invitation):
    invitation.revoke()
    assert not invitation.is_pending
    assert resolve_token(Invitation, invitation.token).state is TokenState.REVOKED


def test_refresh_token_rotates_and_clears_acceptance(invitation):
    old = invitation.token
    invitation.accepted_at = timezone.now()
    invitation.save()
    invitation.refresh_token()
    invitation.refresh_from_db()
    assert invitation.token != old
    assert invitation.accepted_at is None
    assert invitation.is_pending


def test_invitation_link_purpose_is_the_role(invitation):
    assert invitation.link_purpose == "Recruiter"


def test_accept_url_still_uses_the_token(invitation):
    assert invitation.token in invitation.accept_url()
