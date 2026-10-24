#!/bin/sh
set -eu

echo "[entrypoint] Waiting for database..."
python - <<'PY'
import os
import sys
import time

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django

django.setup()

from django.db import connection

last_error = None
for attempt in range(1, 31):
    try:
        connection.ensure_connection()
        print(f"[entrypoint] Database ready after {attempt} attempt(s).")
        break
    except Exception as exc:  # noqa: BLE001 - cần in lỗi để chẩn đoán
        last_error = exc
        print(f"[entrypoint] Database not ready ({attempt}/30): {exc}", flush=True)
        time.sleep(2)
else:
    print(f"[entrypoint] Cannot connect to database: {last_error}", file=sys.stderr)
    sys.exit(1)
PY

echo "[entrypoint] Applying migrations..."
python manage.py migrate --noinput

echo "[entrypoint] Collecting static files..."
python manage.py collectstatic --noinput --clear

echo "[entrypoint] Starting Gunicorn..."
exec gunicorn config.wsgi:application \
    --bind 0.0.0.0:8000 \
    --workers "${GUNICORN_WORKERS:-3}" \
    --threads "${GUNICORN_THREADS:-2}" \
    --timeout "${GUNICORN_TIMEOUT:-60}" \
    --graceful-timeout 30 \
    --access-logfile - \
    --access-logformat '%(h)s "%(m)s %(U)s" %(s)s %(b)s %(L)s' \
    --error-logfile -
