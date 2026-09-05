"""Publishing, feed visibility and expiry."""

from datetime import timedelta

import pytest
from django.utils import timezone

from exchange import services
from exchange.models import ANON_CLIENT, ExchangeRequirement
from exchange.tests.conftest import set_exchange_feature


def test_publishing_needs_the_exchange_feature(job, responder, requester):
    set_exchange_feature(requester, False)
    with pytest.raises(services.ExchangeError) as excinfo:
        services.publish_requirement(job)
    assert "Agency plan" in str(excinfo.value)
    assert ExchangeRequirement.objects.count() == 0


def test_publish_copies_the_job_and_defaults_the_expiry(job, requester_owner):
    requirement = services.publish_requirement(job, created_by=requester_owner)
    assert requirement.title == job.title
    assert requirement.location == "Pune"
    assert [s.name for s in requirement.skills.all()] == ["Django"]
    assert requirement.fee_split_pct == 50
    assert requirement.status == ExchangeRequirement.OPEN
    assert requirement.expires_at > timezone.now()


def test_publish_validates_the_split_and_the_budget(job):
    with pytest.raises(services.ExchangeError):
        services.publish_requirement(job, fee_split_pct=140)
    with pytest.raises(services.ExchangeError):
        services.publish_requirement(job, budget_ctc_min=100, budget_ctc_max=50)


def test_feed_shows_partner_requirements_and_hides_your_own(requester, responder, requirement):
    assert list(services.feed(responder)) == [requirement]
    assert list(services.feed(requester)) == []


def test_feed_hides_partner_only_requirements_from_non_partners(outsider, requirement):
    assert list(services.feed(outsider)) == []
    assert requirement.is_visible_to(outsider) is False


def test_network_requirements_reach_the_whole_network(outsider, network_requirement):
    assert list(services.feed(outsider)) == [network_requirement]


def test_blocking_a_partner_removes_their_requirements_from_the_feed(
    responder, requirement, partnership
):
    services.block_partner(partnership, responder)
    assert list(services.feed(responder)) == []


def test_feed_filters_by_skill_location_and_budget(responder, requirement):
    from jobs.models import Skill

    django = Skill.objects.get(company=requirement.company, name="Django")
    assert list(services.feed(responder, skills=[django])) == [requirement]
    other = Skill.objects.create(company=responder, name="Golang")
    assert list(services.feed(responder, skills=[other])) == []
    assert list(services.feed(responder, location="pun")) == [requirement]
    assert list(services.feed(responder, location="Berlin")) == []
    assert list(services.feed(responder, budget_min=1000000)) == [requirement]
    assert list(services.feed(responder, budget_min=9000000)) == []
    assert list(services.feed(responder, query="django")) == [requirement]


def test_expired_requirements_leave_the_feed(responder, requirement):
    requirement.expires_at = timezone.now() - timedelta(days=1)
    requirement.save(update_fields=["expires_at"])
    assert requirement.is_expired is True
    assert requirement.is_open is False
    assert list(services.feed(responder)) == []


def test_expire_requirements_closes_past_due_rows(requirement):
    requirement.expires_at = timezone.now() - timedelta(minutes=1)
    requirement.save(update_fields=["expires_at"])
    assert services.expire_requirements() == 1
    requirement.refresh_from_db()
    assert requirement.status == ExchangeRequirement.CLOSED
    assert services.expire_requirements() == 0


def test_expire_requirements_command(requirement):
    from io import StringIO

    from django.core.management import call_command

    requirement.expires_at = timezone.now() - timedelta(minutes=1)
    requirement.save(update_fields=["expires_at"])
    out = StringIO()
    call_command("expire_requirements", stdout=out)
    assert "Expired 1 requirement(s)." in out.getvalue()
    requirement.refresh_from_db()
    assert requirement.status == ExchangeRequirement.CLOSED


def test_client_name_is_anonymised_for_network_visibility(
    requester, responder, outsider, network_requirement
):
    assert network_requirement.client_label_for(requester) == "Big Bank Ltd"
    assert network_requirement.client_label_for(responder) == ANON_CLIENT
    assert network_requirement.client_label_for(outsider) == ANON_CLIENT


def test_partners_see_the_client_name_on_a_partners_only_requirement(
    responder, outsider, requirement
):
    assert requirement.client_label_for(responder) == "Big Bank Ltd"
    assert requirement.client_label_for(outsider) == ANON_CLIENT
    assert requirement.client_label_for(None) == ANON_CLIENT


def test_close_requirement_is_owner_only(requirement, responder, requester):
    with pytest.raises(services.ExchangeError):
        services.close_requirement(requirement, responder)
    services.close_requirement(requirement, requester)
    requirement.refresh_from_db()
    assert requirement.status == ExchangeRequirement.CLOSED
