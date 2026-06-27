#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

PYTHON_BIN="${PYTHON_BIN:-python3}"
VENV_DIR="${VENV_DIR:-.venv}"
VENV_PY="$VENV_DIR/bin/python"

if [[ ! -x "$VENV_PY" ]]; then
    "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

"$VENV_PY" -m pip install --upgrade pip setuptools wheel
"$VENV_PY" -m pip install -e ".[dev]"

echo "Bootstrap complete: $VENV_PY"
