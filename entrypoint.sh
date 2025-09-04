#!/usr/bin/env bash
set -euo pipefail

REQ="/app/source/requirements.txt"

if [ "${SKIP_PIP_INSTALL:-0}" != "1" ]; then
  if [ -f "$REQ" ]; then
    echo "Installing Python deps..."
    python -m pip install --upgrade pip
    python -m pip install --no-cache-dir -r "$REQ"
  fi
fi
cd /app
exec python -m source.__main__
