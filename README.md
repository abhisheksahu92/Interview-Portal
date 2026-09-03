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
- **Team invitations** — owners invite teammates by email with a role; a signed
  token link (7-day expiry) creates the membership on accept.
- **Billing** — FREE/PRO plans metered on open jobs, Stripe Checkout + customer
  portal + webhooks; with no Stripe keys the plan/usage page still works.
- **REST API** — DRF viewsets for everything, token auth (checked before session
  auth, so anonymous calls get `401`), OpenAPI schema + Swagger UI.

## Apps
| App | Responsibility |
| --- | --- |
| `core` | Company (tenant), User (email login), Membership/roles, TenantMiddleware, auth + base templates |
| `jobs` | Domain only: jobs, configurable pipeline stages, applications, stage reviews, candidate profiles, transition services |
| `assessments` | Question banks, assessments, attempts, Claude-powered generation/grading, recruiter + candidate screens |
| `api` | DRF viewsets, token auth, OpenAPI schema (drf-spectacular) |
| `billing` | Plans, per-company subscriptions, Stripe checkout/portal/webhooks, open-job plan limits |
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
at `/accounts/signup/`.

## Key URLs
| Path | What |
| --- | --- |
| `/` | Landing page (redirects logged-in users to their home) |
| `/accounts/login/` | Email + password login (emails are case-insensitive) |
| `/accounts/signup/` | Candidate signup |
| `/accounts/signup/company/` | Company (tenant) signup |
| `/accounts/logout/` | GET shows a confirm page; POST signs out |
| `/dashboard/` | Recruiter/owner dashboard |
| `/workspace/jobs/<id>/` | Job pipeline kanban |
| `/queue/` | Interviewer review queue |
| `/portal/` | Candidate portal |
| `/openings/` | Public job board |
| `/assessments/questions/` | Question bank |
| `/api/v1/` | REST API root |
| `/api/docs/` | Swagger UI (schema at `/api/schema/`) |
| `/billing/` | Plan, usage and upgrade |
| `/billing/webhook/` | Stripe webhook endpoint (POST, no auth, signature-verified) |
| `/settings/members/` | Members and invitations |
| `/healthz/` | Liveness probe (`ok`, no auth, no DB) |
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
| `EMAIL_FILE_PATH` | `BASE_DIR/sent_emails` | directory for `django.core.mail.backends.filebased.EmailBackend` |
| `MEDIA_ROOT` | `BASE_DIR/media` | on-disk root for uploads when no S3/R2 bucket is set |
| `STRIPE_SECRET_KEY` / `STRIPE_PUBLISHABLE_KEY` / `STRIPE_WEBHOOK_SECRET` / `STRIPE_PRICE_ID_PRO` | empty | enable Stripe billing; unset = plan/usage shown, upgrade disabled |
| `CSRF_TRUSTED_ORIGINS` | empty | **required in production**, comma-separated, scheme included (`https://app.example.com`) |
| `SECURE_SSL_REDIRECT` | on when `DEBUG=False` | turn off behind a plain-HTTP host |
| `SECURE_HSTS_SECONDS` | `31536000` outside DEBUG | start lower on a custom apex domain |
| `CONN_MAX_AGE` | `60` outside DEBUG/tests | persistent DB connections; must stay `0` under pytest |
| `LOG_LEVEL` / `DJANGO_LOG_LEVEL` | `INFO` | logging goes to stdout |
| `AWS_STORAGE_BUCKET_NAME` / `AWS_S3_REGION_NAME` / `AWS_S3_ENDPOINT_URL` / `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` | empty | set the bucket to move media (resumes) to S3/Cloudflare R2 |
| `POSTGRES_DB` / `POSTGRES_USER` / `POSTGRES_PASSWORD` | `interview_portal` / `interview` / `interview` | used by the compose `db` service |

## Tests and checks
```bash
.venv/bin/ruff check .
.venv/bin/python manage.py check
.venv/bin/python manage.py makemigrations --check --dry-run
.venv/bin/pytest                                  # full suite
.venv/bin/python manage.py spectacular --file /dev/null   # schema must be warning-free
```
Tests run on SQLite and never need `collectstatic`; static files are served by
WhiteNoise, with manifest hashing enabled only outside `DEBUG`/tests
(`python manage.py collectstatic` before a production deploy).

## Invitations

Owners invite teammates from `/settings/members/`: pick an email + role, and the
app stores an `Invitation` with a random token that expires after 7 days and
mails a link to `/accounts/invite/<token>/`. Accepting creates the `Membership`
(signing up first if the invitee has no account). Pending invitations can be
resent or revoked from the same page. With the default console email backend the
link is printed to the server log, which is enough for local testing.

## Billing

`billing/` meters **open jobs** per company:

- `Plan` rows (`FREE`, `max_open_jobs=1`; `PRO`, `max_open_jobs=25`) are seeded by
  a data migration.
- Each company gets a `Subscription` lazily (first visit to `/billing/`, a Stripe
  checkout, or `manage.py provision_subscriptions`).
- A `pre_save` signal on `jobs.Job` raises `ValidationError` when a save would push
  the company past its open-job limit. Companies with **no** `Subscription` row are
  never metered, so fixtures and imports predating billing keep working. The web
  job form catches the error and shows an upgrade link.

Stripe env vars (all optional — without them `/billing/` still shows plan and
usage, only upgrade/portal buttons are disabled):

| Var | Where to find it |
| --- | --- |
| `STRIPE_SECRET_KEY` | Stripe dashboard → Developers → API keys (`sk_test_...`) |
| `STRIPE_PUBLISHABLE_KEY` | same page (`pk_test_...`) |
| `STRIPE_PRICE_ID_PRO` | Products → your Pro price (`price_...`), recurring monthly |
| `STRIPE_WEBHOOK_SECRET` | Developers → Webhooks → your endpoint (`whsec_...`) |

Webhook URL: **`https://<your-domain>/billing/webhook/`** — subscribe to
`checkout.session.completed`, `customer.subscription.updated` and
`customer.subscription.deleted`. Requests are signature-verified with
`STRIPE_WEBHOOK_SECRET`; the endpoint is CSRF-exempt and unauthenticated by design.

Test-mode setup:

```bash
stripe login
stripe listen --forward-to localhost:8000/billing/webhook/   # prints whsec_...
# put that value in .env as STRIPE_WEBHOOK_SECRET, restart runserver
```
Then upgrade from `/billing/` and pay with the test card `4242 4242 4242 4242`,
any future expiry and any CVC.

Give every existing company a billing record after deploying billing:

```bash
.venv/bin/python manage.py provision_subscriptions
```
(the container entrypoint runs this automatically after `migrate`).

## Resume parsing and AI re-scoring

`assessments/resume.py` extracts plain text from an uploaded resume (PDF via
`pypdf`, DOCX via `python-docx`, plain text otherwise), caps it at 12k characters
and caches it on the candidate profile, re-parsing only when the file changes.
Both parsers are imported lazily, so a deployment without them still runs — it
just gets less text. The text feeds `assessments.ai.summarize_fit`, which writes
`Application.ai_summary` and `ai_fit_score` when a candidate applies.

Applications created while `ANTHROPIC_API_KEY` was unset have no score. Backfill
them (or re-score after a prompt change):

```bash
.venv/bin/python manage.py rescore_applications --missing-only --all
.venv/bin/python manage.py rescore_applications --company demo-staffing
.venv/bin/python manage.py rescore_applications --job 1
```

## Production checklist

1. `SECRET_KEY` set to a long random value, `DEBUG=False`.
2. `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS` (with scheme) point at the real domain.
3. `DATABASE_URL` points at managed Postgres; `CONN_MAX_AGE` left at the default `60`.
4. Object storage configured (`AWS_STORAGE_BUCKET_NAME` + keys) — otherwise resumes
   are lost on every deploy on Fly/Railway.
5. TLS terminated at the edge; `SECURE_SSL_REDIRECT` on (`/healthz/` is exempt).
6. `python manage.py check --deploy` is clean (see below).
7. `migrate` and `provision_subscriptions` run on release; `collectstatic` at build.
8. Stripe live keys + a webhook pointed at `/billing/webhook/`, or leave billing
   in display-only mode.
9. `ANTHROPIC_API_KEY` set if AI screening should be on.
10. A superuser exists (`manage.py createsuperuser`) and `/healthz/` returns `ok`.

`DEBUG=0 SECRET_KEY=<real key> ALLOWED_HOSTS=example.com python manage.py check --deploy`
reports **no warnings**. (Using a short placeholder key raises `security.W009`,
which is about the placeholder, not the configuration.)

## Deployment

The image is a two-stage `python:3.12-slim` build: deps are compiled into a
virtualenv in the builder stage, the runtime stage carries only `libpq5` +
`curl`, runs as the non-root user `app` (uid 10001), runs `collectstatic` at
build time (with a throwaway `SECRET_KEY`, `DEBUG=False`, so manifest hashing
is exercised in CI rather than at boot) and has a `HEALTHCHECK` on `/healthz/`.

`scripts/entrypoint.sh` is the entrypoint: it waits for the database, runs
`migrate`, runs `provision_subscriptions`, optionally runs `seed_demo`
(`SEED_DEMO=1`), then execs gunicorn.
Passing any argument other than `gunicorn` runs that command instead
(`docker compose run --rm web python manage.py createsuperuser`).

| Var | Purpose |
| --- | --- |
| `SEED_DEMO=1` | load demo data after migrating (idempotent) |
| `SKIP_MIGRATE=1` | skip migrations (set on Fly, whose `release_command` migrates) |
| `DB_WAIT_TIMEOUT` | seconds to wait for the DB, default `60` |
| `PORT` | gunicorn bind port, default `8000` |
| `GUNICORN_WORKERS` / `GUNICORN_THREADS` / `GUNICORN_TIMEOUT` | `3` / `2` / `60` |

See the **Production checklist** above before the first deploy; the biggest item
is S3/R2 media storage, since uploaded resumes on local disk are lost on every
deploy on Fly and Railway.

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
the S3/R2 vars (see the env table) as secrets, or (single machine only)
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

## Accounts, sessions and errors

- **Emails are the username and are case-insensitive.** They are stored lower-cased
  (`UserManager.create_user`, `User.save`, the signup forms and `Invitation`), a
  data migration lowers pre-existing rows (collisions are skipped and logged), and
  `core.backends.CaseInsensitiveEmailBackend` matches legacy mixed-case rows.
- **Logout is POST-only.** `GET /accounts/logout/` renders a confirmation page;
  every "Sign out" control in the UI posts a form.
- **The active workspace sticks.** `User.last_company` records the last tenant a
  user had active; `TenantMiddleware` falls back to it before the first membership,
  so a re-login lands back in the same workspace. Switching companies and accepting
  an invitation update it.
- **HTMX**: `base.html` puts `hx-headers='{"X-CSRFToken": ...}'` on `<body>`, so bare
  `hx-post` buttons need no per-element token. `core.middleware.HtmxRedirectMiddleware`
  turns a login redirect on an `HX-Request` into `204` + `HX-Redirect`, so an expired
  session sends the browser to the login page instead of swapping a login form into a
  fragment.
- **Error pages**: branded `400/403/404` templates extend `base.html`;
  `500.html` is deliberately standalone (no context processors, no DB, no manifest).
