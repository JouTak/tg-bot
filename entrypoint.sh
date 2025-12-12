#!/usr/bin/env bash
set -euo pipefail

REQ="/app/source/requirements.txt"
INIT_SQL="/init.sql"

if [ -n "${DB_HOST:-}" ]; then
  echo "Waiting for MySQL at ${DB_HOST}:${DB_PORT}..."
  until mysql -h"${MYSQL_HOST}" -P"${MYSQL_PORT}" -u"${MYSQL_USER}" -p"${MYSQL_PASS}" -e "SELECT 1" >/dev/null 2>&1; do
    sleep 2
  done
fi

if [ -f "$INIT_SQL" ]; then
  echo "Applying init.sql..."
  mysql -h"${MYSQL_HOST}" -P"${MYSQL_PORT}" -u"${MYSQL_USER}" -p"${MYSQL_PASSWORD}" < "$INIT_SQL"
fi

if [ "${SKIP_PIP_INSTALL:-0}" != "1" ]; then
  if [ -f "$REQ" ]; then
    echo "Installing Python deps..."
    python -m pip install --upgrade pip
    python -m pip install --no-cache-dir -r "$REQ"
  fi
fi
cd /app
exec python -m source.__main__
