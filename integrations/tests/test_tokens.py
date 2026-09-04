"""Per-company API tokens ride on a service user, not on a human."""

import pytest
from rest_framework.authtoken.models import Token

from core.models import Membership
from integrations import tokens

pytestmark = pytest.mark.django_db


def test_issue_creates_a_service_user_with_recruiter_membership(company):
    token = tokens.issue_token(company)

    assert token.user.email == f"api@{company.slug}.local"
    assert token.user.role_in(company) == Membership.RECRUITER


def test_the_service_user_cannot_log_in_with_a_password(company):
    token = tokens.issue_token(company)
    assert not token.user.has_usable_password()


def test_issuing_twice_rotates_rather_than_duplicates(company):
    first = tokens.issue_token(company)
    second = tokens.issue_token(company)

    assert first.key != second.key
    assert Token.objects.filter(user=second.user).count() == 1
    assert tokens.get_token(company).key == second.key


def test_revoke_removes_the_token(company):
    tokens.issue_token(company)
    assert tokens.revoke_token(company) is True
    assert tokens.get_token(company) is None
    assert tokens.revoke_token(company) is False


def test_get_token_before_issuing_is_none(company):
    assert tokens.get_token(company) is None


def test_each_company_gets_its_own_service_account(company, other_company):
    a = tokens.issue_token(company)
    b = tokens.issue_token(other_company)

    assert a.user != b.user
    assert a.user.role_in(other_company) is None


def test_masking_keeps_only_the_edges():
    masked = tokens.masked("0123456789abcdef")
    assert masked.startswith("012345")
    assert masked.endswith("cdef")
    assert "6789ab" not in masked
    assert tokens.masked("") == ""
    assert tokens.masked("short") == "•" * 5
