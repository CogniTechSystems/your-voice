#!/usr/bin/env bash
# Shared configuration for the Linux and WSL helper scripts.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

is_wsl_windows_mount() {
  grep -qi microsoft /proc/version 2>/dev/null && [[ "$ROOT" == /mnt/* ]]
}

# A checkout on a Windows drive may also be used from Windows, so WSL keeps its virtual
# environment and data on the Linux filesystem, where SQLite locking is reliable.
if is_wsl_windows_mount; then
  VENV="${YV_VENV:-$HOME/.venvs/your-voice}"
  export YV_DATA_DIR="${YV_DATA_DIR:-$HOME/.local/share/your-voice}"
else
  VENV="${YV_VENV:-$ROOT/backend/.venv}"
fi
