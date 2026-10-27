#!/usr/bin/env bash
# Start the application. Configuration is read from YV_* environment variables or .env.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

if [[ ! -x "$VENV/bin/your-voice" ]]; then
  echo "The backend is not installed. Run scripts/setup.sh first." >&2
  exit 1
fi
exec "$VENV/bin/your-voice" "$@"
