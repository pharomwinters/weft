#!/bin/sh
set -e
cd /app/backend

# Migrates, then creates the first admin from the environment or prints a
# one-time setup token. A bad configuration stops the container here.
python manage.py bootstrap

# Forwarded headers are handled by the app itself (TRUSTED_PROXY_COUNT), so
# uvicorn's own handling is switched off.
exec uvicorn config.asgi:application --host 0.0.0.0 --port 8000 --no-proxy-headers
