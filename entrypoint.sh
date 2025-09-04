#!/usr/bin/env bash
set -euo pipefail

REQ="/app/source/requirements.txt"
MAIN="/app/sourc/__main__.py"

if [ "${SKIP_PIP_INSTALL:-0}" != "1" ]; then
  if [ -f "$REQ" ]; then
    echo "Installing Python deps..."
    python -m pip install --upgrade pip
    python -m pip install --no-cache-dir -r "$REQ"
  fi
fi

if [ -f "$MAIN" ]; then
  exec python "$MAIN"
else
  echo "No main.py found"
  exec /bin/bash
fi
