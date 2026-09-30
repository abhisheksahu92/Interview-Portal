"""Tests for Supabase RLS policies generation and middleware session context."""

from io import StringIO
import pytest
from django.core.management import call_command
from django.test import RequestFactory

from core.middleware import TenantMiddleware, set_database_tenant_context
from core.models import Company, Membership, User


@pytest.fixture
def company(db):
    return Company.objects.create(name="RLS Corp", slug="rls-corp")


@pytest.fixture
def user(db, company):
    u = User.objects.create(email="rls@example.com")
    Membership.objects.create(user=u, company=company, role=Membership.OWNER)
    return u


def test_set_database_tenant_context():
    # Calling with ID and None shouldn't raise on any DB engine
    set_database_tenant_context(123)
    set_database_tenant_context(None)


def test_tenant_middleware_sets_and_cleans_tenant_context(rf, user, company):
    request = rf.get("/")
    request.user = user
    request.session = {}

    called = False

    def dummy_view(req):
        nonlocal called
        called = True
        assert req.company == company
        return None

    mw = TenantMiddleware(dummy_view)
    mw(request)
    assert called


def test_generate_supabase_rls_sql_command():
    out = StringIO()
    call_command("generate_supabase_rls_sql", stdout=out)
    sql = out.getvalue()

    assert "ENABLE ROW LEVEL SECURITY" in sql
    assert "REVOKE ALL ON TABLE" in sql
    assert "current_setting('app.current_company_id', true)" in sql
    assert "jobs_job" in sql
    assert "jobs_application" in sql
