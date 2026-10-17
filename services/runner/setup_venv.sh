#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPOSITORY_ROOT="$(cd -- "$SCRIPT_DIR/../.." && pwd)"
VENV_PATH="$REPOSITORY_ROOT/.venv"
PYTHON_BIN="${PYTHON_BIN:-python3}"
PLAYWRIGHT_BROWSERS_PATH="$VENV_PATH/playwright-browsers"

if [[ ! -x "$VENV_PATH/bin/python" ]]; then
  "$PYTHON_BIN" -m venv "$VENV_PATH"
fi

"$VENV_PATH/bin/python" -m pip install --upgrade pip
"$VENV_PATH/bin/python" -m pip install -r "$SCRIPT_DIR/requirements.txt"
PLAYWRIGHT_BROWSERS_PATH="$PLAYWRIGHT_BROWSERS_PATH" \
  "$VENV_PATH/bin/python" -m playwright install chromium

echo "Virtual environment ready at $VENV_PATH"
echo "Playwright browsers ready at $PLAYWRIGHT_BROWSERS_PATH"
