#!/usr/bin/env bash
# Create the local Postgres role and database for development.
#
# Local dev deliberately runs the same major version as production (Neon, PG 18).
# SQLite was the old default and hid real differences: JSONField behaviour,
# constraint deferral, and `select_for_update` all diverge on it.
#
# Usage: scripts/setup_local_db.sh [password]
set -euo pipefail

DB=interview
ROLE=interview_app
PW="${1:-$(python3 -c 'import secrets;print(secrets.token_urlsafe(18))')}"

sudo -u postgres psql -v ON_ERROR_STOP=1 \
  -c "DROP DATABASE IF EXISTS ${DB};" \
  -c "DROP ROLE IF EXISTS ${ROLE};" \
  -c "CREATE ROLE ${ROLE} LOGIN PASSWORD '${PW}' CREATEDB;" \
  -c "CREATE DATABASE ${DB} OWNER ${ROLE};"

echo
echo "Put this in .env:"
echo "DATABASE_URL=postgres://${ROLE}:${PW}@127.0.0.1:5432/${DB}"
echo
echo "Then: python manage.py migrate"
