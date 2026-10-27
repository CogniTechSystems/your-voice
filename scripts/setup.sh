#!/usr/bin/env bash
# Install the backend into a virtual environment and build the frontend.
# Usage: scripts/setup.sh [--skip-frontend]
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

PYTHON="${PYTHON:-python3}"
SKIP_FRONTEND=false
[[ "${1:-}" == "--skip-frontend" ]] && SKIP_FRONTEND=true

echo "Creating virtual environment at $VENV"
"$PYTHON" -m venv "$VENV"
"$VENV/bin/python" -m pip install --quiet --upgrade pip
"$VENV/bin/python" -m pip install --quiet -e "$ROOT/backend[dev]"

if [[ "$SKIP_FRONTEND" == true ]]; then
  echo "Skipping the frontend build."
elif command -v npm >/dev/null 2>&1; then
  (cd "$ROOT/frontend" && npm ci && npm run build)
else
  echo "npm was not found. Install Node.js 20 or later, or rerun with --skip-frontend." >&2
  exit 1
fi

echo "Setup complete. Start the application with scripts/start.sh"
