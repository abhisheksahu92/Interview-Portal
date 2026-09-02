# Interview Portal v2 — Architecture Spec (shared by all agents)

Goal: turn the old single-company Django demo into a multi-tenant, configurable hiring SaaS
for small IT services / staffing firms, with AI-assisted screening.

## Stack
- Django 5.x, Python 3.12, Django REST Framework, HTMX + Bootstrap 5 (CDN) for UI, django-environ for settings.
- DB: PostgreSQL in prod (DATABASE_URL); SQLite fallback for local dev/tests.
- Anthropic Python SDK for AI features (agent working on it must load the `claude-api` skill).
- pytest + pytest-django, ruff, GitHub Actions CI.

## Apps (each agent owns ONLY its app directory unless told otherwise)
- `core/`        — Company (tenant), CustomUser (email login), Membership(user, company, role: OWNER/RECRUITER/INTERVIEWER), TenantMiddleware (request.company), base templates, auth views. [Foundation agent]
- `jobs/`        — Job (FK company), PipelineStage (per job, ordered, configurable: e.g. Screening, L1, L2, HR, Offer), Application (candidate x job, current_stage), StageReview (application, stage, reviewer, decision, feedback), CandidateProfile (user, resume, experience, notice period, skills M2M). Skill is a per-company model, NOT hardcoded choices.
- `assessments/` — Skill-tagged QuestionBank/Question (MCQ + free text), Assessment (per job stage, time limit, pass mark), Attempt (application, answers JSON, score), AI: generate questions from a job description, grade free-text answers, summarize a resume against job requirements (Claude API; key via ANTHROPIC_API_KEY; must degrade gracefully when key missing).
- `api/`         — DRF viewsets/serializers for everything above, token auth, OpenAPI schema (drf-spectacular), scoped by request.company.
- `web/`         — HTMX/Bootstrap 5 templates + views: recruiter dashboard (pipeline kanban), candidate portal (apply, take assessment, track status), interviewer review screens, company settings (stages, skills, members).

## Shared-file rules
- `interview_portal/settings.py`, root `urls.py`, `requirements.txt`, `pyproject.toml` are written ONCE by the foundation agent, which pre-registers all five apps and includes all five url modules (`core.urls`, `jobs.urls`, `assessments.urls`, `api.urls`, `web.urls`) with stub urlpatterns.
- Later agents may only APPEND lines to requirements.txt and must NOT reorder/rewrite shared files.
- Cross-app imports: jobs -> core; assessments -> jobs, core; api/web -> all. Never import web/api from domain apps.
- Every app ships migrations and tests. `python manage.py check` and `pytest` must pass before an agent finishes.
- All secrets from env only. Never commit .env, sqlite DBs, or media.

## Legacy
Old apps `candidate/`, `employee/`, `empadmin/`, `dashboard/`, old `jobs/` and old templates/static are deleted by the foundation agent. Old `db.sqlite3`, `media/`, `.env`, and leaked Dockerfile token are removed.
