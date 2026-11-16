#!/bin/sh
set -e
# Apply database migrations before starting (idempotent).
if [ "${SKIP_MIGRATIONS:-false}" != "true" ]; then
  alembic upgrade head
fi
exec "$@"
