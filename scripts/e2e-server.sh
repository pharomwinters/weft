#!/bin/sh
# Starts the real server for the end-to-end tests: a scratch database named
# `e2e` on the development Postgres, the built frontend, port 8010.
# Run by Playwright (frontend/playwright.config.ts); not meant for anything else.
set -eu

ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT"

# The dev database URL is resolved exactly as the tests resolve it
# (DATABASE_URL, else .env.dev, else compose.dev.yml's Postgres). Only the
# database named `e2e` is ever dropped.
E2E_DATABASE_URL=$(uv run python - <<'PY'
import os
import sys
from urllib.parse import urlsplit, urlunsplit

sys.path.insert(0, "backend")
import config.settings_test  # noqa: F401  (resolves DATABASE_URL into the environment)
import psycopg

dev = urlsplit(os.environ["DATABASE_URL"])
with psycopg.connect(urlunsplit(dev), autocommit=True) as connection:
    connection.execute("DROP DATABASE IF EXISTS e2e WITH (FORCE)")
    connection.execute("CREATE DATABASE e2e")
print(urlunsplit(dev._replace(path="/e2e")))
PY
)

(cd frontend && pnpm build)

export DATABASE_URL="$E2E_DATABASE_URL"
export DJANGO_SETTINGS_MODULE=config.settings
export PUBLIC_URL=http://localhost:8010
export FRONTEND_DIST="$ROOT/frontend/dist"
SECRET_KEY=$(uv run python -c "import secrets; print(secrets.token_hex(32))")
TOTP_ENCRYPTION_KEY=$(uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
export SECRET_KEY TOTP_ENCRYPTION_KEY
unset INITIAL_ADMIN_EMAIL INITIAL_ADMIN_PASSWORD TRUSTED_PROXY_COUNT

# A fresh database means a fresh instance: forget the last run's accounts.
rm -f frontend/e2e/.state.json
uv run python backend/manage.py bootstrap > frontend/e2e/.bootstrap.log

cd backend
exec uv run uvicorn config.asgi:application --host 127.0.0.1 --port 8010 --no-proxy-headers
