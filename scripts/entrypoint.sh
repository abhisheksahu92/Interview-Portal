#!/usr/bin/env bash
# Container entrypoint: wait for the DB, migrate, optionally seed, then serve.
#
#   docker run ... web                 -> gunicorn (default CMD)
#   docker run ... web gunicorn        -> same
#   docker run ... web <anything else> -> exec'd verbatim (e.g. bash, manage.py ...)
#
# Env:
#   DATABASE_URL      postgres://... (a sqlite URL skips the wait)
#   SEED_DEMO=1       run `manage.py seed_demo` after migrating (idempotent)
#   SKIP_MIGRATE=1    do not run migrations (e.g. Fly release_command already did)
#   DB_WAIT_TIMEOUT   seconds to wait for the DB, default 60
#   PORT              gunicorn bind port, default 8000
#   GUNICORN_WORKERS / GUNICORN_THREADS / GUNICORN_TIMEOUT
set -euo pipefail

log() { printf '[entrypoint] %s\n' "$*" >&2; }

wait_for_db() {
    local url="${DATABASE_URL:-}"
    if [ -z "$url" ] || [[ "$url" == sqlite* ]]; then
        log "no external database configured; skipping wait"
        return 0
    fi
    local timeout="${DB_WAIT_TIMEOUT:-60}"
    local waited=0
    log "waiting for database (timeout ${timeout}s)..."
    until python - <<'PY'
import os, sys
from urllib.parse import urlparse
import socket

url = urlparse(os.environ["DATABASE_URL"])
host = url.hostname or "localhost"
port = url.port or 5432
try:
    with socket.create_connection((host, port), timeout=3):
        pass
except OSError as exc:
    print(f"not ready: {exc}", file=sys.stderr)
    sys.exit(1)
PY
    do
        if [ "$waited" -ge "$timeout" ]; then
            log "database not reachable after ${timeout}s; giving up"
            exit 1
        fi
        sleep 2
        waited=$((waited + 2))
    done
    log "database is reachable"
}

if [ "$#" -gt 0 ] && [ "$1" != "gunicorn" ]; then
    exec "$@"
fi

wait_for_db

if [ "${SKIP_MIGRATE:-0}" != "1" ]; then
    log "running migrations"
    python manage.py migrate --noinput
else
    log "SKIP_MIGRATE=1; skipping migrations"
fi

log "provisioning billing subscriptions"
python manage.py provision_subscriptions

if [ "${SEED_DEMO:-0}" = "1" ]; then
    log "seeding demo data"
    python manage.py seed_demo
fi

WORKERS="${GUNICORN_WORKERS:-3}"
THREADS="${GUNICORN_THREADS:-2}"
TIMEOUT="${GUNICORN_TIMEOUT:-60}"
BIND="0.0.0.0:${PORT:-8000}"

log "starting gunicorn on ${BIND} (${WORKERS} workers x ${THREADS} threads)"
exec gunicorn interview_portal.wsgi:application \
    --bind "$BIND" \
    --workers "$WORKERS" \
    --threads "$THREADS" \
    --timeout "$TIMEOUT" \
    --graceful-timeout 30 \
    --keep-alive 5 \
    --max-requests 1000 \
    --max-requests-jitter 100 \
    --access-logfile - \
    --error-logfile - \
    --capture-output
