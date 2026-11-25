#!/bin/sh
set -e
# run migrations unless SKIP_MIGRATIONS=1
if [ "${SKIP_MIGRATIONS:-0}" != "1" ]; then
  alembic upgrade head
fi
exec "$@"
