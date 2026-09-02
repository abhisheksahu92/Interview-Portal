# Interview Portal v2

Multi-tenant hiring platform for small IT services / staffing firms, with AI-assisted screening.
Django 5 + DRF + HTMX/Bootstrap 5. See `ARCHITECTURE.md` for the full design.

## Apps
| App | Responsibility |
| --- | --- |
| `core` | Company (tenant), User (email login), Membership/roles, TenantMiddleware, auth + base templates |
| `jobs` | Jobs, configurable pipeline stages, applications, stage reviews, candidate profiles |
| `assessments` | Question banks, assessments, attempts, Claude-powered generation/grading |
| `api` | DRF viewsets, token auth, OpenAPI schema (drf-spectacular) |
| `web` | HTMX dashboards: recruiter pipeline, candidate portal, interviewer reviews, settings |

## Local setup
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python manage.py migrate
python manage.py seed_demo      # demo company + users, password: demo1234
python manage.py runserver
```

## Checks
```bash
.venv/bin/ruff check .
.venv/bin/python manage.py check
.venv/bin/pytest
```

## Docker
```bash
cp .env.example .env   # set DATABASE_URL=postgres://interview:interview@db:5432/interview_portal
docker compose up --build
```

Legacy v1 code lives in `legacy/` and is excluded from lint/tests. Do not import from it.
