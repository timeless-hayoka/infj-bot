#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

./scripts/bootstrap_venv.sh

PYTHONNOUSERSITE=1
VENV_PY="${VENV_DIR:-.venv}/bin/python"
DRIFT="./scripts/drift"

"$VENV_PY" -m pip install -q -e ".[dev]"

"$DRIFT" doctor --json
"$DRIFT" status --json || true
"$DRIFT" release --json || "$DRIFT" version --json

ANCHOR_GATE=(
  tests/test_roadmap_phases.py
  tests/test_trinity_caseflow.py
  tests/test_trinity_sarif_pipeline.py
  tests/test_trinity_sarif_adapter.py
  tests/test_anchor_analytics.py
  tests/test_anchor_dashboard.py
  tests/test_anchor_cli.py
  tests/test_sync_logs.py
)

"$VENV_PY" -m pytest -q "${ANCHOR_GATE[@]}"

chmod +x ./scripts/anchor_release_smoke.sh
./scripts/anchor_release_smoke.sh

echo "ANCHOR bootstrap complete."
echo "Next: ./scripts/drift dashboard"
