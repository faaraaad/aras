#!/usr/bin/env bash
set -e

# ==============================================================================
# Container Entrypoint Script
# Handles automatic database migrations and static collection before starting services
# ==============================================================================

echo "==> Starting container entrypoint..."

# If command is starting the web server, automatically apply migrations and static collection
if [ "$1" = "gunicorn" ] || [ "$1" = "python" -a "$2" = "manage.py" -a "$3" = "runserver" ]; then
    echo "==> Applying database migrations..."
    python manage.py migrate --noinput

    echo "==> Collecting static files..."
    python manage.py collectstatic --noinput --clear || true
fi

echo "==> Executing application command: $@"
exec "$@"
