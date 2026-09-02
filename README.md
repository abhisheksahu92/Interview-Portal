# Interview Portal v2

Multi-tenant hiring platform for small IT services / staffing firms, with AI-assisted screening.
Django 5 + DRF + HTMX/Bootstrap 5. See `ARCHITECTURE.md` for the full design.

## Features
- **Multi-tenant** — every company is a tenant; `TenantMiddleware` puts the active
  company on `request.company` and all queries/permissions are scoped to it.
  Users can belong to several companies and switch between them.
- **Roles** — OWNER / RECRUITER / INTERVIEWER memberships, plus external candidates.
- **Configurable pipelines** — each job gets default stages (Screening, Assessment,
  L1, L2, HR, Offer) that recruiters can rename, reorder, add to or delete.
- **Recruiter workspace** — KPI dashboard, drag-free kanban board per job with
  HTMX advance/reject/review actions, member and skill settings.
- **Interviewer queue** — every interview/HR-stage application awaiting your review,
  with inline PASS/FAIL/HOLD + rating + feedback (a PASS advances, a FAIL rejects).
- **Candidate portal** — browse/search open roles, apply, edit a profile with resume
  upload, and track each application's stage progress.
- **Assessments** — skill-tagged question bank (MCQ + free text), per-stage timed
  assessments with pass marks, candidate attempts with automatic MCQ grading.
- **AI (Claude)** — generate screening questions from a job description, grade
  free-text answers, and summarize a resume against the job into an
  `ai_summary` + `ai_fit_score` (fired automatically on every new application).
  All AI degrades gracefully: with no `ANTHROPIC_API_KEY` it logs and no-ops.
- **REST API** — DRF viewsets for everything, token auth, OpenAPI schema + Swagger UI.

## Apps
| App | Responsibility |
| --- | --- |
| `core` | Company (tenant), User (email login), Membership/roles, TenantMiddleware, auth + base templates |
| `jobs` | Domain only: jobs, configurable pipeline stages, applications, stage reviews, candidate profiles, transition services |
| `assessments` | Question banks, assessments, attempts, Claude-powered generation/grading, recruiter + candidate screens |
| `api` | DRF viewsets, token auth, OpenAPI schema (drf-spectacular) |
| `web` | **Canonical server-rendered UI**: landing, recruiter dashboard/kanban, candidate portal, interviewer reviews, company settings |

## Quick start
```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env                    # DEBUG=True, SQLite by default
.venv/bin/python manage.py migrate
.venv/bin/python manage.py seed_demo    # demo company, jobs, questions, applications
.venv/bin/python manage.py runserver
```
Then open http://127.0.0.1:8000/.

`seed_demo` is idempotent (safe to re-run) and creates the **Demo Staffing** company
with 3 skills, 2 open jobs and their pipelines, 3 manual questions, one assessment on
job 1's Assessment stage, 3 applicants spread across stages and one review.

### Demo logins — password `demo1234` for all
| Email | Role |
| --- | --- |
| `owner@demo.test` | OWNER — dashboard, jobs, members, skills |
| `recruiter@demo.test` | RECRUITER — dashboard, jobs, question bank |
| `interviewer@demo.test` | INTERVIEWER — review queue only |
| `candidate@demo.test` | Candidate — portal, browse and apply |
| `asha@demo.test`, `ben@demo.test`, `chen@demo.test` | Candidates with live applications |

Create your own tenant instead at `/accounts/signup/company/`, or a candidate account
at `/accounts/signup/candidate/`.

## Key URLs
| Path | What |
| --- | --- |
| `/` | Landing page (redirects logged-in users to their home) |
| `/accounts/login/` | Email + password login |
| `/dashboard/` | Recruiter/owner dashboard |
| `/workspace/jobs/<id>/` | Job pipeline kanban |
| `/queue/` | Interviewer review queue |
| `/portal/` | Candidate portal |
| `/openings/` | Public job board |
| `/assessments/questions/` | Question bank |
| `/api/v1/` | REST API root |
| `/api/docs/` | Swagger UI (schema at `/api/schema/`) |
| `/admin/` | Django admin |

API clients authenticate with `POST /api/v1/auth/token/` (email + password) and then
send `Authorization: Token <key>`.

## Environment variables
Copy `.env.example` to `.env`; everything is read from the environment.

| Var | Default | Notes |
| --- | --- | --- |
| `SECRET_KEY` | insecure dev value | **must** be set in production |
| `DEBUG` | `False` | `True` locally; also selects non-manifest static storage |
| `ALLOWED_HOSTS` | `localhost,127.0.0.1` | comma-separated |
| `DATABASE_URL` | `sqlite:///db_v2.sqlite3` | e.g. `postgres://user:pass@db:5432/interview_portal` |
| `ANTHROPIC_API_KEY` | empty | enables the Claude features; unset = AI disabled |
| `EMAIL_BACKEND` / `EMAIL_HOST` / `EMAIL_PORT` / `EMAIL_HOST_USER` / `EMAIL_HOST_PASSWORD` / `EMAIL_USE_TLS` / `DEFAULT_FROM_EMAIL` | console backend | outbound mail |
| `POSTGRES_DB` / `POSTGRES_USER` / `POSTGRES_PASSWORD` | `interview_portal` / `interview` / `interview` | used by the compose `db` service |

## Tests and checks
```bash
.venv/bin/ruff check .
.venv/bin/python manage.py check
.venv/bin/python manage.py makemigrations --check --dry-run
.venv/bin/pytest                                  # 139 tests
.venv/bin/python manage.py spectacular --file /dev/null   # schema must be warning-free
```
Tests run on SQLite and never need `collectstatic`; static files are served by
WhiteNoise, with manifest hashing enabled only outside `DEBUG`/tests
(`python manage.py collectstatic` before a production deploy).

## Deployment

The image is a two-stage `python:3.12-slim` build: deps are compiled into a
virtualenv in the builder stage, the runtime stage carries only `libpq5` +
`curl`, runs as the non-root user `app` (uid 10001), runs `collectstatic` at
build time (with a throwaway `SECRET_KEY`, `DEBUG=False`, so manifest hashing
is exercised in CI rather than at boot) and has a `HEALTHCHECK` on `/healthz/`.

`scripts/entrypoint.sh` is the entrypoint: it waits for the database, runs
`migrate`, optionally runs `seed_demo` (`SEED_DEMO=1`), then execs gunicorn.
Passing any argument other than `gunicorn` runs that command instead
(`docker compose run --rm web python manage.py createsuperuser`).

| Var | Purpose |
| --- | --- |
| `SEED_DEMO=1` | load demo data after migrating (idempotent) |
| `SKIP_MIGRATE=1` | skip migrations (set on Fly, whose `release_command` migrates) |
| `DB_WAIT_TIMEOUT` | seconds to wait for the DB, default `60` |
| `PORT` | gunicorn bind port, default `8000` |
| `GUNICORN_WORKERS` / `GUNICORN_THREADS` / `GUNICORN_TIMEOUT` | `3` / `2` / `60` |

> **Before the first production deploy** the settings owner must apply
> `interview_portal/settings_checks.md` — most importantly the `/healthz/` view
> (all three platforms' health checks hit it) and S3/R2 media storage, because
> uploaded resumes on local disk are lost on every deploy on Fly and Railway.

### Local Docker

```bash
cp .env.example .env
# set DATABASE_URL=postgres://interview:interview@db:5432/interview_portal
docker compose up --build
docker compose exec web python manage.py seed_demo   # optional demo data
```
PostgreSQL 16 (healthchecked) plus the app on http://localhost:8000/. Uploads
live on the `media` volume, DB data on `pgdata`.

### Single-host production (docker compose)

```bash
docker compose -f docker-compose.yaml -f docker-compose.prod.yaml up -d --build
docker compose -f docker-compose.yaml -f docker-compose.prod.yaml logs -f web
```
The overlay forces `DEBUG=False`, raises the worker count, sets
`restart: always`, caps log files and binds the app to `127.0.0.1:8000` so a
host reverse proxy (nginx/Caddy/Traefik) terminates TLS in front of it. Point
`ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS` at your real domain in `.env`.

### Fly.io

`fly.toml` is checked in: region `bom`, `release_command` runs migrations
before new machines take traffic, `http_service` health-checks `/healthz/`,
`force_https` on.

```bash
fly launch --no-deploy --copy-config --name interview-portal --region bom
fly postgres create --name interview-portal-db --region bom
fly postgres attach interview-portal-db          # injects DATABASE_URL
fly secrets set SECRET_KEY="$(python -c 'import secrets;print(secrets.token_urlsafe(50))')"
fly secrets set ANTHROPIC_API_KEY=sk-ant-...     # optional; unset = AI disabled
fly deploy
fly ssh console -C "python manage.py createsuperuser"
```
If you pick a different app name, update `app`, `ALLOWED_HOSTS` and
`CSRF_TRUSTED_ORIGINS` in `fly.toml`. Resume uploads need object storage — set
the S3/R2 vars from `settings_checks.md` as secrets, or (single machine only)
uncomment the `[[mounts]]` block and `fly volumes create media`.

### Railway

`railway.json` builds from the `Dockerfile` and starts via the entrypoint, with
the health check on `/healthz/`.

```bash
railway login
railway init                     # or `railway link` to an existing project
railway add --database postgres   # injects DATABASE_URL
railway variables --set SECRET_KEY=... --set DEBUG=False \
  --set ALLOWED_HOSTS=<service>.up.railway.app \
  --set CSRF_TRUSTED_ORIGINS=https://<service>.up.railway.app
railway up
```
Use the private `*.railway.internal` Postgres URL to avoid egress charges.
Railway's filesystem is ephemeral, so configure S3/R2 media storage.

### CI/CD

`.github/workflows/ci.yml` lints and tests every branch.
`.github/workflows/deploy.yml` runs on pushes to `main`: ruff, `check --deploy`,
`makemigrations --check`, pytest and `collectstatic`, then `flyctl deploy`. The
deploy job is **skipped** unless the `FLY_API_TOKEN` repository secret exists,
so the workflow is safe to merge before you have a Fly account:

```bash
fly tokens create deploy -x 999999h     # paste into Settings > Secrets > FLY_API_TOKEN
```

Legacy v1 code lives in `legacy/` and is excluded from lint/tests. Do not import from it.
