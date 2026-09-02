# settings.py changes requested by the deploy agent

Written by the **deploy** agent. The deploy agent does not edit `settings.py` or
root `urls.py` — this file is the request list for whoever owns those.
Everything below is required (or strongly recommended) for the Docker / Fly.io /
Railway deployments now checked in (`Dockerfile`, `fly.toml`, `railway.json`,
`docker-compose*.yaml`, `scripts/entrypoint.sh`, `.github/workflows/deploy.yml`).

Assumed existing helpers: `env = environ.Env(...)`, `DEBUG`, `TESTING`.

---

## 1. BLOCKER — health check endpoint (root `urls.py`)

The container `HEALTHCHECK`, the Fly `[[http_service.checks]]` and the Railway
`healthcheckPath` all hit `GET /healthz/`, which does not exist yet. Without it
containers will be reported unhealthy and Fly/Railway deploys will roll back.

Add to `interview_portal/urls.py`:

```python
path("healthz/", lambda r: HttpResponse("ok")),
```

(with `from django.http import HttpResponse`). It must be **unauthenticated**,
**not tenant-scoped**, and must not touch the database, so the check stays fast
and stays green during a DB blip. It must also answer for the internal
health-check `Host` header — either keep `.fly.dev`/`localhost` in
`ALLOWED_HOSTS` (already done in `fly.toml`) or exempt this view.

---

## 2. Proxy / TLS termination

Fly and Railway terminate TLS at the edge and forward plain HTTP, so Django
must learn the original scheme from the header or every `request.is_secure()`
check, absolute URL and secure-cookie decision will be wrong:

```python
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = True
```

## 3. HTTPS redirect (outside DEBUG only)

```python
SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=not (DEBUG or TESTING))
```

Keep it env-overridable: `fly.toml` sets `force_https = true` at the edge, and a
plain-HTTP `docker compose` host or a local `docker run` needs it off. It must
not apply to `/healthz/` in a way that breaks the check — with
`SECURE_PROXY_SSL_HEADER` set and Fly's `force_https`, health checks arrive with
`X-Forwarded-Proto: https` and are fine; if you see redirect loops on the
health check, add `SECURE_REDIRECT_EXEMPT = [r"^healthz/$"]`.

## 4. Secure cookies

```python
SESSION_COOKIE_SECURE = not (DEBUG or TESTING)
CSRF_COOKIE_SECURE = not (DEBUG or TESTING)
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = False       # HTMX reads the token from the cookie
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True
```

## 5. `CSRF_TRUSTED_ORIGINS` from the environment

Required for any POST/HTMX request on the deployed domain. `fly.toml` already
exports `CSRF_TRUSTED_ORIGINS=https://interview-portal.fly.dev`; Railway users
set it to `https://<service>.up.railway.app`.

```python
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])
```

Entries **must** include the scheme. Please also allow `ALLOWED_HOSTS` to carry
a leading-dot wildcard (`.fly.dev`) — the current comma-split list already
does, just don't strip dots.

## 6. HSTS

```python
SECURE_HSTS_SECONDS = env.int("SECURE_HSTS_SECONDS", default=0 if (DEBUG or TESTING) else 31536000)
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
```

Default to `0` in DEBUG/tests. Note the one-year header is sticky in browsers —
keep it env-overridable so a custom apex domain can start at e.g. `3600`.

## 7. `LOGGING` to stdout

Containers have no log files; Docker, Fly and Railway all collect stdout/stderr.
Gunicorn is already started with `--access-logfile - --error-logfile -
--capture-output`, so Django only needs a stream handler:

```python
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {"format": "%(asctime)s %(levelname)s %(name)s %(message)s"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "verbose"},
    },
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL", default="INFO")},
    "loggers": {
        "django": {"handlers": ["console"], "level": env("DJANGO_LOG_LEVEL", default="INFO"), "propagate": False},
        "django.request": {"handlers": ["console"], "level": "WARNING", "propagate": False},
        # assessments.ai logs when ANTHROPIC_API_KEY is missing — keep it visible.
        "assessments": {"handlers": ["console"], "level": "INFO", "propagate": False},
    },
}
```

## 8. Database connection reuse

Every gunicorn worker currently opens a fresh connection per request. Managed
Postgres on Fly/Railway has a low connection cap, so:

```python
DATABASES = {"default": env.db_url("DATABASE_URL", default=f"sqlite:///{BASE_DIR / 'db_v2.sqlite3'}")}
DATABASES["default"]["CONN_MAX_AGE"] = env.int("CONN_MAX_AGE", default=0 if (DEBUG or TESTING) else 60)
DATABASES["default"]["CONN_HEALTH_CHECKS"] = not (DEBUG or TESTING)
```

`CONN_MAX_AGE` **must stay 0 under pytest** (persistent connections break the
test-database teardown). Also consider
`DATABASES["default"].setdefault("OPTIONS", {})["connect_timeout"] = 5` so a
dead DB fails fast instead of hanging a worker for the gunicorn timeout.

Fly's `postgres attach` injects a `postgres://` URL — `env.db_url` handles it.
Railway injects `DATABASE_URL` on the Postgres plugin; use the **private**
(`*.railway.internal`) URL to avoid egress charges.

## 9. Media storage — resumes will be lost without this

`MEDIA_ROOT = BASE_DIR / "media"` is **ephemeral** on both Fly.io and Railway:
the container filesystem is recreated on every deploy, restart and machine
move, and Fly's `auto_stop_machines` plus more than one machine means uploads
land on whichever instance served the POST. `CandidateProfile.resume`
(`upload_to="resumes/"`) is real user data, so local disk is not acceptable in
production.

Requested: object storage via `django-storages`, env-gated so local dev and
tests keep using the filesystem.

```python
# requirements.txt (append): django-storages[s3]==1.14.4  and  boto3
if env("AWS_STORAGE_BUCKET_NAME", default=""):
    STORAGES["default"] = {
        "BACKEND": "storages.backends.s3.S3Storage",
        "OPTIONS": {
            "bucket_name": env("AWS_STORAGE_BUCKET_NAME"),
            "region_name": env("AWS_S3_REGION_NAME", default="auto"),
            "endpoint_url": env("AWS_S3_ENDPOINT_URL", default=None),  # Cloudflare R2
            "access_key": env("AWS_ACCESS_KEY_ID", default=""),
            "secret_key": env("AWS_SECRET_ACCESS_KEY", default=""),
            "default_acl": "private",
            "querystring_auth": True,   # resumes must be signed URLs, never public
            "file_overwrite": False,
            "signature_version": "s3v4",
        },
    }
```

Cloudflare R2 is the cheapest fit (no egress fees): set
`AWS_S3_ENDPOINT_URL=https://<account>.r2.cloudflarestorage.com` and
`AWS_S3_REGION_NAME=auto`. Resume downloads must go through signed URLs or a
permission-checked Django view — never a public bucket.

Interim fallback (single-instance only) is a Fly volume mounted at
`/app/media`; the `[[mounts]]` block in `fly.toml` is commented out for this.

## 10. Nice-to-haves

- `DATA_UPLOAD_MAX_MEMORY_SIZE` / `FILE_UPLOAD_MAX_MEMORY_SIZE` — cap resume
  upload size (e.g. 10 MB) and validate the extension in the form.
- Keep `STATIC_ROOT.mkdir(...)` — the Dockerfile runs `collectstatic` as the
  non-root `app` user and relies on `/app/staticfiles` being writable.
- `python manage.py check --deploy --fail-level ERROR` runs in
  `.github/workflows/deploy.yml`; items 2-6 above are exactly what it flags.
