"""Connector adapters: gating on credentials, payload shape, no network."""

import pytest

from integrations.connectors import ADAPTERS, adapter_for
from integrations.connectors.base import ConnectorResult, employee_payload
from integrations.models import ConnectorConfig, ConnectorRun
from integrations.services import probe_connection, start_background_check

pytestmark = pytest.mark.django_db


class FakeResponse:
    def __init__(self, status_code=201):
        self.status_code = status_code


def make(company, kind, **settings):
    return ConnectorConfig.objects.create(
        company=company, kind=kind, settings=settings, active=True
    )


def test_every_kind_has_an_adapter():
    assert set(ADAPTERS) == {kind for kind, _ in ConnectorConfig.KIND_CHOICES}


def test_an_unconfigured_connector_reports_not_configured(company):
    config = make(company, ConnectorConfig.KEKA)
    adapter = config.adapter()

    assert adapter.configured() is False
    assert sorted(adapter.missing_settings()) == ["api_key", "subdomain"]

    result = adapter.test_connection()
    assert result.status == ConnectorResult.SKIPPED
    assert "not configured" in result.detail


def test_a_configured_connector_probes_the_vendor(company, monkeypatch):
    config = make(company, ConnectorConfig.KEKA, api_key="k", subdomain="acme")
    adapter = config.adapter()
    seen = {}

    def fake_request(self, method, path, json=None):
        seen.update(method=method, path=path)
        return FakeResponse(200)

    monkeypatch.setattr(type(adapter), "request", fake_request)
    result = adapter.test_connection()

    assert result.ok
    assert seen == {"method": "GET", "path": "/employees?limit=1"}


def test_a_vendor_error_becomes_an_error_result(company, monkeypatch):
    config = make(company, ConnectorConfig.KEKA, api_key="k", subdomain="acme")
    adapter = config.adapter()
    monkeypatch.setattr(
        type(adapter), "request", lambda *a, **k: FakeResponse(503)
    )
    assert adapter.test_connection().status == ConnectorResult.ERROR


def test_a_transport_exception_becomes_an_error_result(company, monkeypatch):
    config = make(company, ConnectorConfig.KEKA, api_key="k", subdomain="acme")
    adapter = config.adapter()

    def boom(*a, **k):
        raise TimeoutError("vendor timeout")

    monkeypatch.setattr(type(adapter), "request", boom)
    result = adapter.test_connection()
    assert result.status == ConnectorResult.ERROR
    assert "TimeoutError" in result.detail


def test_probe_connection_service_logs_a_run(company):
    config = make(company, ConnectorConfig.ZOHO_PEOPLE)
    result = probe_connection(config)

    assert result.status == ConnectorResult.SKIPPED
    assert ConnectorRun.objects.get(config=config).status == ConnectorRun.SKIPPED


def test_employee_payload_pulls_from_application_and_offer(application):
    from datetime import date

    from offers.models import Offer

    Offer.objects.create(
        application=application, salary=900000, joining_date=date(2026, 4, 1)
    )
    record = employee_payload(application)

    assert record["email"] == "cand@example.com"
    assert record["first_name"] == "Asha"
    assert record["full_name"] == "Asha Rao"
    assert record["job_title"] == "Python Developer"
    assert record["joining_date"] == "2026-04-01"
    assert record["phone"] == "+919000000000"


def test_employee_payload_survives_a_missing_offer(application):
    record = employee_payload(application)
    assert record["joining_date"] is None
    assert record["salary"] is None


def test_keka_maps_to_vendor_field_names(company, application, monkeypatch):
    config = make(company, ConnectorConfig.KEKA, api_key="k", subdomain="acme")
    adapter = config.adapter()

    assert adapter.base_url() == "https://acme.keka.com/api/v1"
    body = adapter.employee_body(application)
    assert body["email"] == "cand@example.com"
    assert body["firstName"] == "Asha"
    assert body["sourceApplicationId"] == application.pk


def test_zoho_people_wraps_fields_in_inputdata(company, application):
    import json

    config = make(company, ConnectorConfig.ZOHO_PEOPLE, api_key="t", data_center="in")
    adapter = config.adapter()

    assert adapter.base_url() == "https://people.zoho.in/people/api"
    assert adapter.headers()["Authorization"] == "Zoho-oauthtoken t"
    fields = json.loads(adapter.employee_body(application)["inputData"])
    assert fields["EmailID"] == "cand@example.com"
    assert fields["LastName"] == "Rao"


def test_greythr_nests_the_employee_and_keeps_a_reference(company, application):
    config = make(company, ConnectorConfig.GREYTHR, api_key="k", domain="acme.greythr.com")
    adapter = config.adapter()

    assert adapter.base_url() == "https://acme.greythr.com/api/v2"
    body = adapter.employee_body(application)
    assert body["employee"]["personalEmail"] == "cand@example.com"
    assert body["externalRef"] == f"ip-application-{application.pk}"


def test_base_url_setting_overrides_the_derived_url(company):
    config = make(
        company, ConnectorConfig.KEKA, api_key="k", subdomain="acme", base_url="https://x/api"
    )
    assert config.adapter().base_url() == "https://x/api"


def test_push_hire_posts_once_when_configured(company, application, monkeypatch):
    config = make(company, ConnectorConfig.GREYTHR, api_key="k", domain="acme.greythr.com")
    adapter = config.adapter()
    calls = []

    def fake_request(self, method, path, json=None):
        calls.append((method, path, json))
        return FakeResponse(201)

    monkeypatch.setattr(type(adapter), "request", fake_request)
    result = adapter.push_hire(application)

    assert result.ok
    assert len(calls) == 1
    assert calls[0][:2] == ("POST", "/employee/v2/employees")


def test_a_non_hrms_connector_declines_hires(company, application):
    config = make(company, ConnectorConfig.BACKGROUND_CHECK, api_key="k", base_url="https://bgv")
    assert config.adapter().push_hire(application).status == ConnectorResult.SKIPPED


def test_an_hrms_connector_declines_background_checks(company, candidate):
    config = make(company, ConnectorConfig.KEKA, api_key="k", subdomain="a")
    assert config.adapter().start_check(candidate).status == ConnectorResult.SKIPPED


def test_background_check_posts_the_candidate_and_packages(company, candidate, monkeypatch):
    config = make(
        company,
        ConnectorConfig.BACKGROUND_CHECK,
        api_key="k",
        base_url="https://bgv.test",
        packages="identity, education",
    )
    adapter = config.adapter()
    calls = []

    def fake_request(self, method, path, json=None):
        calls.append((method, path, json))
        return FakeResponse(202)

    monkeypatch.setattr(type(adapter), "request", fake_request)
    result = adapter.start_check(candidate)

    assert result.ok
    method, path, body = calls[0]
    assert (method, path) == ("POST", "/v1/checks")
    assert body["packages"] == ["identity", "education"]
    assert body["candidate"]["email"] == "cand@example.com"
    assert body["reference"] == f"ip-candidate-{candidate.pk}"


def test_start_background_check_without_a_connector_is_a_no_op(company, candidate):
    assert start_background_check(candidate, company) is None
    assert ConnectorRun.objects.count() == 0


def test_start_background_check_logs_a_run(company, candidate, monkeypatch):
    config = make(company, ConnectorConfig.BACKGROUND_CHECK, api_key="k", base_url="https://b")
    monkeypatch.setattr(
        type(config.adapter()),
        "request",
        lambda *a, **k: FakeResponse(200),
    )
    run = start_background_check(candidate, company)
    assert run.status == ConnectorRun.OK
    assert run.config_id == config.pk


def test_adapter_for_an_unknown_kind_is_none(company):
    config = ConnectorConfig(company=company, kind="NOPE")
    assert adapter_for(config) is None


def test_connector_kinds_are_unique_per_company(company):
    from django.db import IntegrityError

    make(company, ConnectorConfig.KEKA, api_key="k")
    with pytest.raises(IntegrityError):
        make(company, ConnectorConfig.KEKA, api_key="k2")


def test_configs_are_scoped_to_their_company(company, other_company):
    make(company, ConnectorConfig.KEKA, api_key="k")
    assert ConnectorConfig.objects.for_company(other_company).count() == 0
    assert ConnectorConfig.objects.for_company(None).count() == 0
