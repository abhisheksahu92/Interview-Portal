# Supabase Database Security & Row Level Security (RLS) Strategy

## 1. Threat Model & Executive Summary

Interview Portal is a multi-tenant B2B hiring platform hosted on Render with database persistence provided by **Supabase PostgreSQL**.

While Django's ORM and custom managers (`core.tenancy.TenantQuerySet`, `CompanyScopedViewSetMixin`) enforce company-scoping at the application layer, defense-in-depth is essential:
1. **Direct PostgREST Exposure**: Supabase by default exposes a public REST API (`/rest/v1/...`). Any compromise or public exposure of the `anon` API key would allow unauthenticated attackers to query all tables directly if Row Level Security is disabled.
2. **Leaked Service Keys & Multi-role Access**: External tools, analytics workers, or microservices querying the database directly must have tenant boundaries enforced by PostgreSQL itself.
3. **Defense-in-Depth Against ORM Bugs**: In the event of an inadvertent `Model.objects.all()` or un-scoped join, database-level RLS acts as the final gate blocking cross-tenant data access.

---

## 2. Row Level Security (RLS) Architecture

### A. Session Context Variable (`app.current_company_id`)
PostgreSQL supports dynamic session variables via `current_setting('app.current_company_id', true)`.
- When Django processes a request, `TenantMiddleware` extracts the tenant and executes:
  ```sql
  SET app.current_company_id = '<company_id>';
  ```
- Upon request completion, the middleware executes `RESET app.current_company_id;` to ensure pooled connections return cleanly to the pool without retaining stale tenant state.

### B. Table Isolation Strategy
1. **Public/Global Reference Tables** (e.g., `jobs_skill`, `marketplace_questionpack`):
   - RLS is enabled.
   - Public read access is permitted where applicable; write access is restricted.
2. **Direct Tenant Tables** (e.g., `jobs_job`, `assessments_question`, `billing_invoice`, `contracting_contractor`):
   - Policy:
     ```sql
     CREATE POLICY tenant_isolation_<table_name> ON <table_name>
       FOR ALL
       TO authenticated, service_role, postgres
       USING (company_id::text = NULLIF(current_setting('app.current_company_id', true), ''))
       WITH CHECK (company_id::text = NULLIF(current_setting('app.current_company_id', true), ''));
     ```
3. **Indirect / Child Tables** (e.g., `jobs_pipelinestage`, `jobs_application`):
   - Policy:
     ```sql
     CREATE POLICY tenant_isolation_<table_name> ON <table_name>
       FOR ALL
       TO authenticated, service_role, postgres
       USING (job_id IN (
         SELECT id FROM jobs_job WHERE company_id::text = NULLIF(current_setting('app.current_company_id', true), '')
       ))
       WITH CHECK (job_id IN (
         SELECT id FROM jobs_job WHERE company_id::text = NULLIF(current_setting('app.current_company_id', true), '')
       ));
     ```
4. **PostgREST Hardening**:
   - `REVOKE ALL ON TABLE <table_name> FROM anon, public;` on all company-sensitive tables to block direct unauthenticated scraping.

### C. Architectural Boundary: User Identity (`core_user`)
- **Policy**: `core_user` has `USING (TRUE) WITH CHECK (TRUE)` for authenticated roles.
- **Rationale**: User identity, credential verification, and account creation precede tenant resolution (`app.current_company_id` is necessarily null during initial unauthenticated requests like login and signup). Attempting to isolate `core_user` by `last_company_id` at the RLS level breaks authentication, multi-company account switching, and candidate portal access.
- **Enforcement Layers**: Tenant boundaries for user records are deliberately enforced at the **application layer**:
  1. `Membership` model joins (`core.models.Membership`) which *are* strictly isolated by company.
  2. Role-based view guards (`@role_required`, `role_in(company)`).
  3. API tenant scoping (`CompanyScopedViewSetMixin`, `get_queryset().for_company()`).
  4. Candidate PII encapsulation (`jobs_candidateprofile` is bounded to `user_id`, preventing cross-company member snooping).

---

## 3. Operational Deployment & Maintenance

### Automatic DDL Generation
A dedicated Django management command inspects all models and relationships to generate the current DDL:
```bash
python manage.py generate_supabase_rls_sql --output docs/supabase_rls_policies.sql
```

### Applying Policies to Supabase
Run the generated script directly via Supabase SQL Editor, Supabase CLI, or via deployment migrations:
```bash
psql "$DATABASE_URL" -f docs/supabase_rls_policies.sql
```
