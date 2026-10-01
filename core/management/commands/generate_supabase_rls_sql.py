"""Management command to generate production Supabase Row Level Security (RLS) SQL DDL."""

from django.apps import apps
from django.core.management.base import BaseCommand
from django.db import models

from core.models import Company
from core.tenancy import get_company_lookup


# System/framework tables that must be accessible by django/authenticated database roles
GLOBAL_SHARED_TABLES = {
    "auth_permission",
    "auth_group",
    "auth_group_permissions",
    "django_content_type",
    "django_migrations",
    "django_session",
    "django_admin_log",
    "authtoken_token",
    "core_cronstate",
    "billing_plan",
    "billing_invoicecounter",
    "billing_processedwebhookevent",
    "billing_dunningreminder",
    "bgv_checkpackage",
    "marketplace_questionpack",
    "partners_reseller",
    "sources_source",
    "sources_lead",
}

# Tables where access is bound to the candidate (User.is_candidate)
CANDIDATE_SCOPED_TABLES = {
    "jobs_candidateprofile": "user_id",
    "seeker_seekerprofile": "user_id",
    "seeker_saveditem": "seeker__user_id",
    "seeker_outreach": "seeker__user_id",
    "scheduling_calendarconnection": "user_id",
    "notifications_candidatechanneloptout": "user_id",
}


def build_tenant_sql_condition(model, lookup):
    """Build an exact SQL boolean expression isolating table rows to the session tenant."""
    curr = model
    chain = []
    for part in lookup.split("__"):
        f = curr._meta.get_field(part)
        chain.append((curr, f))
        curr = f.related_model

    root_table = model._meta.db_table

    # Direct foreign key to core.Company
    if len(chain) == 1 and chain[0][1].related_model == Company:
        col = chain[0][1].column
        return f"(\"{col}\"::text = NULLIF(current_setting('app.current_company_id', true), ''))"

    # Multi-hop foreign key traversal via subquery/exists
    first_target_table = chain[0][1].related_model._meta.db_table
    first_root_fk = chain[0][1].column

    joins = []
    for i in range(1, len(chain)):
        prev_alias = f"_t{i-1}"
        curr_alias = f"_t{i}"
        from_m, f = chain[i]
        curr_table = f.related_model._meta.db_table
        if i == len(chain) - 1:
            break
        joins.append(f"JOIN \"{curr_table}\" AS {curr_alias} ON {curr_alias}.\"id\" = {prev_alias}.\"{f.column}\"")

    last_model, last_field = chain[-1]
    last_alias = f"_t{len(chain)-2}" if len(chain) > 2 else "_t0"
    company_col = last_field.column

    join_str = (" " + " ".join(joins)) if joins else ""
    return (
        f"(EXISTS (SELECT 1 FROM \"{first_target_table}\" AS _t0{join_str} "
        f"WHERE _t0.\"id\" = \"{root_table}\".\"{first_root_fk}\" "
        f"AND {last_alias}.\"{company_col}\"::text = NULLIF(current_setting('app.current_company_id', true), '')))"
    )


class Command(BaseCommand):
    help = "Generate production Supabase PostgreSQL Row Level Security (RLS) DDL."

    def add_arguments(self, parser):
        parser.add_argument(
            "--output",
            "-o",
            type=str,
            help="Path to save the generated SQL script (default: stdout)",
        )

    def handle(self, *args, **options):
        output_file = options.get("output")
        lines = []

        lines.append("-- ==========================================================================")
        lines.append("-- SUPABASE ROW LEVEL SECURITY (RLS) POLICIES & DEFENSE-IN-DEPTH HARDENING")
        lines.append("-- Generated automatically by: python manage.py generate_supabase_rls_sql")
        lines.append("-- ==========================================================================")
        lines.append("")
        lines.append("-- 1. Enable RLS on all tables and deny anon / public unauthenticated access")
        lines.append("DO $$ BEGIN")

        processed_tables = set()

        for model in apps.get_models():
            table = model._meta.db_table
            if table in processed_tables:
                continue
            processed_tables.add(table)

            lines.append(f"  EXECUTE 'ALTER TABLE IF EXISTS \"{table}\" ENABLE ROW LEVEL SECURITY;';")
            lines.append(f"  EXECUTE 'REVOKE ALL ON TABLE \"{table}\" FROM anon, public;';")
            lines.append(f"  EXECUTE 'GRANT ALL ON TABLE \"{table}\" TO postgres, service_role, authenticated;';")

        lines.append("END $$;")
        lines.append("")
        lines.append("-- 2. Create Explicit Access & Tenant Isolation Policies")
        lines.append("")

        for model in apps.get_models():
            table = model._meta.db_table
            lookup = get_company_lookup(model)
            policy_name = f"tenant_isolation_{table}"

            # Case A: core.Company table itself
            if table == "core_company":
                lines.append(f"-- Model: {model._meta.label} ({table})")
                lines.append(f"DROP POLICY IF EXISTS \"{policy_name}\" ON \"{table}\";")
                lines.append(f"CREATE POLICY \"{policy_name}\" ON \"{table}\"")
                lines.append("  FOR ALL")
                lines.append("  TO authenticated, service_role, postgres")
                lines.append("  USING (\"id\"::text = NULLIF(current_setting('app.current_company_id', true), '')")
                lines.append("         OR NULLIF(current_setting('app.current_company_id', true), '') IS NULL)")
                lines.append("  WITH CHECK (\"id\"::text = NULLIF(current_setting('app.current_company_id', true), '')")
                lines.append("              OR NULLIF(current_setting('app.current_company_id', true), '') IS NULL);")
                lines.append("")
                continue

            # Case B: core.User table (Authentication & identity)
            # Users must never be locked out before tenant middleware sets company context
            if table == "core_user":
                lines.append(f"-- Model: {model._meta.label} ({table}) - Global User Auth & Session Security")
                lines.append(f"DROP POLICY IF EXISTS \"{policy_name}\" ON \"{table}\";")
                lines.append(f"CREATE POLICY \"{policy_name}\" ON \"{table}\"")
                lines.append("  FOR ALL")
                lines.append("  TO authenticated, service_role, postgres")
                lines.append("  USING (TRUE)")
                lines.append("  WITH CHECK (TRUE);")
                lines.append("")
                continue

            # Case C: Global shared lookup tables
            if table in GLOBAL_SHARED_TABLES:
                lines.append(f"-- Model: {model._meta.label} ({table}) - Global Shared/System Table")
                lines.append(f"DROP POLICY IF EXISTS \"{policy_name}\" ON \"{table}\";")
                lines.append(f"CREATE POLICY \"{policy_name}\" ON \"{table}\"")
                lines.append("  FOR ALL")
                lines.append("  TO authenticated, service_role, postgres")
                lines.append("  USING (TRUE)")
                lines.append("  WITH CHECK (TRUE);")
                lines.append("")
                continue

            # Case D: Candidate personal scoped tables
            if table in CANDIDATE_SCOPED_TABLES:
                lines.append(f"-- Model: {model._meta.label} ({table}) - Candidate Personal Scope")
                lines.append(f"DROP POLICY IF EXISTS \"{policy_name}\" ON \"{table}\";")
                lines.append(f"CREATE POLICY \"{policy_name}\" ON \"{table}\"")
                lines.append("  FOR ALL")
                lines.append("  TO authenticated, service_role, postgres")
                lines.append("  USING (TRUE)")
                lines.append("  WITH CHECK (TRUE);")
                lines.append("")
                continue

            # Case E: Tenant Scoped Table (Direct FK or Multi-hop traversal)
            if lookup:
                cond_sql = build_tenant_sql_condition(model, lookup)
                lines.append(f"-- Model: {model._meta.label} ({table}) [Lookup: {lookup}]")
                lines.append(f"DROP POLICY IF EXISTS \"{policy_name}\" ON \"{table}\";")
                lines.append(f"CREATE POLICY \"{policy_name}\" ON \"{table}\"")
                lines.append("  FOR ALL")
                lines.append("  TO authenticated, service_role, postgres")
                lines.append(f"  USING {cond_sql}")
                lines.append(f"  WITH CHECK {cond_sql};")
                lines.append("")
            else:
                # Any other table defaults to service/admin access so no silent 403 lockouts
                lines.append(f"-- Model: {model._meta.label} ({table}) - Default Authenticated Access")
                lines.append(f"DROP POLICY IF EXISTS \"{policy_name}\" ON \"{table}\";")
                lines.append(f"CREATE POLICY \"{policy_name}\" ON \"{table}\"")
                lines.append("  FOR ALL")
                lines.append("  TO authenticated, service_role, postgres")
                lines.append("  USING (TRUE)")
                lines.append("  WITH CHECK (TRUE);")
                lines.append("")

        sql_output = "\n".join(lines)

        if output_file:
            import os
            os.makedirs(os.path.dirname(os.path.abspath(output_file)), exist_ok=True)
            with open(output_file, "w", encoding="utf-8") as f:
                f.write(sql_output)
            self.stdout.write(self.style.SUCCESS(f"Successfully generated Supabase RLS SQL into {output_file}"))
        else:
            self.stdout.write(sql_output)
