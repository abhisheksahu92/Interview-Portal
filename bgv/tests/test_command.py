"""`manage.py bgv_poll` drives the mock provider to completion."""

import pytest
from django.core.management import call_command

from bgv import services
from bgv.models import VerificationOrder

pytestmark = pytest.mark.django_db


def test_poll_command_advances_and_completes(company, candidate, package, owner):
    order = services.create_order(company, candidate, package, ordered_by=owner)
    services.record_consent(order, name="Priya Sharma")
    call_command("bgv_poll")
    order.refresh_from_db()
    assert order.status == VerificationOrder.IN_PROGRESS
    call_command("bgv_poll")
    order.refresh_from_db()
    assert order.status == VerificationOrder.COMPLETED


def test_poll_command_leaves_unconsented_orders_alone(company, candidate, package, owner):
    order = services.create_order(company, candidate, package, ordered_by=owner)
    call_command("bgv_poll")
    order.refresh_from_db()
    assert order.status == VerificationOrder.CONSENT_PENDING
