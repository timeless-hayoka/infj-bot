#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if [[ -n "${PYTHON:-}" ]]; then
    runner_python="$PYTHON"
elif [[ -x .venv/bin/python ]]; then
    runner_python=.venv/bin/python
else
    runner_python=python3
fi
exec "$runner_python" scripts/run_validation.py "$@"
