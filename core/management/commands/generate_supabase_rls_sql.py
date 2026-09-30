"""Management command to generate production Supabase Row Level Security (RLS) SQL DDL."""

import sys
from django.apps import apps
from django.core.management.base import BaseCommand
from django.db import models

from core.models import Company
from core.tenancy import TENANT_LOOKUP_MAP, get_company_lookup


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
        lines.append("-- 2. Create Tenant Isolation Policies based on app.current_company_id session context")
        lines.append("")

        for model in apps.get_models():
            table = model._meta.db_table
            lookup = get_company_lookup(model)
            policy_name = f"tenant_isolation_{table}"

            # Direct company FK
            has_direct_company = False
            for f in model._meta.fields:
                if isinstance(f, models.ForeignKey) and f.related_model == Company:
                    has_direct_company = f.column
                    break

            if has_direct_company:
                col = has_direct_company
                lines.append(f"-- Model: {model._meta.label} ({table})")
                lines.append(f"DROP POLICY IF EXISTS \"{policy_name}\" ON \"{table}\";")
                lines.append(f"CREATE POLICY \"{policy_name}\" ON \"{table}\"")
                lines.append("  FOR ALL")
                lines.append("  TO authenticated, service_role, postgres")
                lines.append(f"  USING (\"{col}\"::text = NULLIF(current_setting('app.current_company_id', true), ''))")
                lines.append(f"  WITH CHECK (\"{col}\"::text = NULLIF(current_setting('app.current_company_id', true), ''));")
                lines.append("")
            elif lookup == "job__company":
                # Child of Job (e.g. Application, PipelineStage)
                lines.append(f"-- Model: {model._meta.label} ({table}) via Job")
                lines.append(f"DROP POLICY IF EXISTS \"{policy_name}\" ON \"{table}\";")
                lines.append(f"CREATE POLICY \"{policy_name}\" ON \"{table}\"")
                lines.append("  FOR ALL")
                lines.append("  TO authenticated, service_role, postgres")
                lines.append("  USING (\"job_id\" IN (SELECT id FROM \"jobs_job\" WHERE \"company_id\"::text = NULLIF(current_setting('app.current_company_id', true), '')))")
                lines.append("  WITH CHECK (\"job_id\" IN (SELECT id FROM \"jobs_job\" WHERE \"company_id\"::text = NULLIF(current_setting('app.current_company_id', true), '')));")
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
