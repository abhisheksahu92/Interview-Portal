#!/usr/bin/env bash
# Local development helper: set up .env, install deps, migrate, seed, runserver.
#
#   ./scripts/dev.sh              # migrate + runserver on :8000
#   ./scripts/dev.sh --seed       # also run seed_demo
#   ./scripts/dev.sh --port 8080
set -euo pipefail

cd "$(dirname "$0")/.."

PY="${PY:-.venv/bin/python}"
PORT=8000
SEED=0

while [ "$#" -gt 0 ]; do
    case "$1" in
        --seed) SEED=1; shift ;;
        --port) PORT="$2"; shift 2 ;;
        -h|--help) sed -n '2,8p' "$0"; exit 0 ;;
        *) echo "unknown option: $1" >&2; exit 2 ;;
    esac
done

if [ ! -x "$PY" ]; then
    echo "creating virtualenv in .venv"
    python3 -m venv .venv
    PY=.venv/bin/python
    "$PY" -m pip install --upgrade pip
    "$PY" -m pip install -r requirements.txt
fi

if [ ! -f .env ]; then
    echo "creating .env from .env.example"
    cp .env.example .env
fi

"$PY" manage.py migrate
[ "$SEED" = "1" ] && "$PY" manage.py seed_demo
exec "$PY" manage.py runserver "0.0.0.0:${PORT}"
