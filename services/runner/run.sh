#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPOSITORY_ROOT="$(cd -- "$SCRIPT_DIR/../.." && pwd)"
VENV_PATH="$REPOSITORY_ROOT/.venv"

if [[ ! -x "$VENV_PATH/bin/python" ]]; then
  echo "Project virtual environment is missing. Run services/runner/setup_venv.sh first." >&2
  exit 2
fi

export PLAYWRIGHT_BROWSERS_PATH="${PLAYWRIGHT_BROWSERS_PATH:-$VENV_PATH/playwright-browsers}"
exec "$VENV_PATH/bin/python" "$SCRIPT_DIR/execute.py" "$@"
