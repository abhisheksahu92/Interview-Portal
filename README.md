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

## Docker
```bash
cp .env.example .env   # set DATABASE_URL=postgres://interview:interview@db:5432/interview_portal
docker compose up --build
```
Brings up PostgreSQL 16 plus the app on http://localhost:8000/ (gunicorn, migrations
run on start). Seed demo data with
`docker compose exec web python manage.py seed_demo`.

Legacy v1 code lives in `legacy/` and is excluded from lint/tests. Do not import from it.
