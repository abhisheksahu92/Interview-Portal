# Production Deployment & Operations Runbook

> Last updated: KAN-13 hardening pass.  Update this file whenever the topology or a critical operational procedure changes.

---

## 1. Production Topology

```
Internet
    │
    ▼
Cloudflare (DNS + DDoS + CDN for static)
    │
    ▼
Render Web Service  ──────────────────────────────┐
(Django WSGI / Gunicorn)                           │
    │                                              │
    ├── Supabase PostgreSQL (pooler: pgBouncer)    │
    │   └── Row-Level Security enabled (KAN-6)     │
    │                                              │
    ├── Supabase Storage (resumes, offer PDFs)     │
    │                                              │
    └── Render Redis (Valkey / Redis 7)            │
            │                                      │
            ▼                                      │
    Render Worker Service ◄────────────────────────┘
    (Django run_worker)
        ├── Queue: ai      → AI scoring, question generation
        ├── Queue: email   → Transactional email
        ├── Queue: notify  → Notifications, WebSockets
        ├── Queue: webhook → Outbound webhook delivery
        └── Queue: default → Everything else
```

---

## 2. Render Services

| Service | Type | Plan | Command |
|---|---|---|---|
| `interview-portal` | Web | Starter+ | `gunicorn interview_portal.wsgi` |
| `interview-portal-worker` | Background Worker | Starter | `python manage.py run_worker` |
| `interview-portal-redis` | Redis | Starter | Managed by Render |

### Environment Variables (all services)

| Variable | Required | Description |
|---|---|---|
| `SECRET_KEY` | ✅ | Django secret key (50+ chars) |
| `DATABASE_URL` | ✅ | Supabase pooler connection string |
| `REDIS_URL` | ✅ | Render Redis connection string |
| `ALLOWED_HOSTS` | ✅ | Comma-separated allowed hosts |
| `ANTHROPIC_API_KEY` | ⚠️ | AI features (falls back to Gemini) |
| `GEMINI_API_KEY` | ⚠️ | AI fallback provider (KAN-9) |
| `SENTRY_DSN` | ⚠️ | Error tracking |
| `POSTHOG_PROJECT_KEY` | ⚠️ | Product analytics (KAN-11) |
| `IMAGEKIT_PRIVATE_KEY` | ⚠️ | File storage |
| `IMAGEKIT_URL_ENDPOINT` | ⚠️ | File storage |

> ⚠️ = Strongly recommended for production; AI features degrade gracefully without keys.

---

## 3. Deploy Procedure

### Standard Deploy (code change)

```bash
# 1. Run tests locally first
pytest core/ api/ jobs/ -q

# 2. Push to main → Render auto-deploys web + worker
git push origin main

# 3. Verify deploy
python manage.py check_deploy   # run via Render shell or locally with prod env
```

### Database Migration

Migrations run automatically on web service startup via `release` command in `render.yaml`.

```yaml
# render.yaml excerpt
services:
  - type: web
    buildCommand: pip install -r requirements.txt
    startCommand: gunicorn interview_portal.wsgi
    envVars:
      - key: DJANGO_SETTINGS_MODULE
        value: interview_portal.settings
```

> **Never** run migrations directly against the Supabase pooler (pgBouncer). Use the **direct** connection string (port 5432, not 6543) for migrations. Set `DATABASE_DIRECT_URL` in the release command environment if needed.

---

## 4. Pre-Deploy Checklist

Run `python manage.py check_deploy` before every production push. It validates:

- [ ] `SECRET_KEY` is non-default and long
- [ ] `ALLOWED_HOSTS` is set
- [ ] `DATABASE_URL` points to production
- [ ] `REDIS_URL` is configured (for queues and sessions)
- [ ] `ANTHROPIC_API_KEY` or `GEMINI_API_KEY` is present (AI features)
- [ ] `SENTRY_DSN` is set (observability)
- [ ] File storage is configured (ImageKit / S3)

---

## 5. Worker Operations

### Starting the worker locally

```bash
python manage.py run_worker --queues ai,email,notify,webhook,default
```

### Queue monitoring

```bash
# Queue depths
python manage.py shell -c "from core.queue import get_queue_stats; import json; print(json.dumps(get_queue_stats(), indent=2))"
```

### Draining dead-letter queue

Failed tasks (after 3 retries with exponential backoff) land in `queue:dead`.

```bash
# Inspect dead letters
python manage.py shell -c "
import redis, json
from django.conf import settings
r = redis.from_url(settings.REDIS_URL)
items = r.lrange('queue:dead', 0, -1)
for item in items[:10]:
    print(json.loads(item))
"
```

---

## 6. AI Provider Gateway (KAN-9)

Provider priority: **Anthropic → Gemini → Ollama (local fallback)**

Circuit breaker state is stored in Django cache (Redis in prod). When a provider returns HTTP 429/503/504 it is cooled down for 60 seconds and the next provider in the chain is tried automatically.

### Checking provider status

```bash
python manage.py shell -c "
from core import llm
from django.core.cache import cache
for p in llm._PROVIDER_CHAIN:
    cd = llm._is_provider_cooling_down(p)
    key_ok = llm._provider_has_key(p)
    print(f'{p}: configured={key_ok} cooling_down={cd}')
print('active:', llm.active_provider())
"
```

### Force-clear a stuck cooldown

```bash
python manage.py shell -c "
from core.llm import _clear_provider_cooldown
_clear_provider_cooldown('anthropic')
_clear_provider_cooldown('gemini')
print('Cooldowns cleared')
"
```

---

## 7. Observability

### Log streams

All structured hiring events are emitted under the `hiring` logger:

```
hiring_event event=application.created application_id=42 job_id=7 company_id=3 ...
```

All AI gateway decisions are emitted under `core.llm`:

```
llm_gateway: provider=anthropic latency_ms=1243 tried=['anthropic']
llm_gateway: provider=anthropic cooling_down_for=60s
llm_gateway: provider=gemini latency_ms=892 tried=['anthropic', 'gemini']
```

### Sentry

Sentry is configured via `SENTRY_DSN`. Error tracking is active in production only. Performance tracing is off by default (`SENTRY_TRACES_SAMPLE_RATE=0.0`) — enable at 0.05–0.1 in low-traffic windows.

Key Sentry tags to filter on:
- `environment`: `production` / `staging`
- `release`: git commit SHA (auto-set from `RENDER_GIT_COMMIT`)

### PostHog (KAN-11)

Server-side events captured at key funnel steps:

| Event | Triggered When |
|---|---|
| `application_submitted` | Candidate applies to a job |
| `offer_sent` | Recruiter sends an offer |
| `offer_accepted` | Candidate signs the offer |

The browser snippet (via context processor) captures page views and frontend interactions automatically.

---

## 8. Database: Supabase + RLS

### Connection strings

| Purpose | Port | Variable |
|---|---|---|
| Application (pooled) | 6543 | `DATABASE_URL` |
| Migrations (direct) | 5432 | `DATABASE_DIRECT_URL` (optional) |

### RLS policies

All tables have Row Level Security enabled. Policies enforce tenant isolation using `current_setting('app.current_company_id', true)`, set by `TenantMiddleware` on each request.

To regenerate the RLS SQL:

```bash
python manage.py generate_supabase_rls_sql
# Output: docs/supabase_rls_policies.sql
```

Apply in Supabase SQL editor or via `psql` on the direct connection.

---

## 9. Redis / Valkey

Used for:
- **Queue backend** — job queues (ai, email, notify, webhook, default, dead)
- **Session cache** — `cached_db` session backend
- **Django cache** — AI provider circuit breaker, template fragment caching
- **Delayed tasks** — ZSET-based scheduled task promotion

### Redis key namespaces

| Prefix | Purpose |
|---|---|
| `queue:<name>` | Task queue LISTs |
| `queue:delayed` | Delayed task ZSET (scored by execute_at timestamp) |
| `queue:dead` | Dead letter LIST |
| `llm_cooldown:<provider>` | AI circuit breaker TTL keys |
| `django.cache.*` | Django cache framework |

---

## 10. Scaling Notes

- **Web workers**: Gunicorn with `WEB_CONCURRENCY` workers (default: 4 on Render Starter). Django is sync/WSGI; gevent or uvicorn with ASGI is not required until WebSockets land.
- **Background worker**: One worker process handles all queues. Scale vertically (bigger Render instance) before adding a second worker to avoid double-processing. If you add a second worker, ensure `QUEUE_SYNCHRONOUS=False` and test for idempotency on AI tasks.
- **Database connections**: Supabase pooler (pgBouncer) caps at 60 connections on free tier. With 4 web workers + 1 worker process, Django's persistent connection `CONN_MAX_AGE` should stay at 0 (default) on the pooler — pgBouncer handles connection reuse.

---

## 11. Rollback

```bash
# Render: use the "Rollback" button in the dashboard, or:
git revert HEAD --no-edit
git push origin main

# For a migration rollback (use with care):
python manage.py migrate <app> <previous_migration_number>
```

> Migrations with `AddIndex` / `RemoveIndex` are safe to roll back. Migrations that drop columns or tables are not reversible without data loss.
