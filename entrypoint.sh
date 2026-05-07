#!/usr/bin/env bash
set -euo pipefail

REQ="${REQ_PATH:-/app/source/requirements.txt}"
INIT_SQL="${INIT_SQL_PATH:-/init.sql}"
DEPS_DIR="${PYTHON_DEPS_DIR:-/tmp/tg-itmocraft-deps}"

MYSQL_PORT="${MYSQL_PORT:-3306}"

if [ -n "${MYSQL_HOST:-}" ]; then
  echo "Waiting for MySQL at ${MYSQL_HOST}:${MYSQL_PORT}..."
  until mysql -h"${MYSQL_HOST}" -P"${MYSQL_PORT}" -u"${MYSQL_USER}" -p"${MYSQL_PASS}" -e "SELECT 1" >/dev/null 2>&1; do
    sleep 2
  done
fi

if [ -f "$INIT_SQL" ]; then
  echo "Applying init.sql..."
  mysql -h"${MYSQL_HOST}" -P"${MYSQL_PORT}" -u"${MYSQL_USER}" -p"${MYSQL_PASS}" < "$INIT_SQL"
fi

if [ "${SKIP_PIP_INSTALL:-0}" != "1" ]; then
  if [ -f "$REQ" ]; then
    echo "Installing Python deps from ${REQ}..."
    rm -rf "$DEPS_DIR"
    mkdir -p "$DEPS_DIR"
    python -m pip install --no-cache-dir --upgrade --force-reinstall --ignore-installed --target "$DEPS_DIR" -r "$REQ"
    export PYTHONPATH="${DEPS_DIR}:${PYTHONPATH:-}"
  else
    echo "requirements.txt not found at ${REQ}"
  fi
fi

cd /app
exec python -m source.__main__