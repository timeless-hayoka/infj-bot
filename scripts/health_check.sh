#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

# Activate virtual environment if present
if [[ -f venv/bin/activate ]]; then
    source venv/bin/activate
fi

echo "=== DRIFT Health Check ==="
set +e
python3 tools/selfcheck.py --verbose "$@"
rc=$?
set -e

if [ $rc -ge 2 ]; then
    echo "❌ Critical failures detected (exit code $rc)"
    exit $rc
elif [ $rc -eq 1 ]; then
    echo "⚠️  Warnings present (continuing...)"
fi

if [[ "${LIVE_API_CHECK:-0}" == "1" ]]; then
    echo ""
    echo "=== Live API Check ==="
    python3 -c "
from infj_bot.core.brain import DriftBrain
print(DriftBrain().think('Health check: answer in one short sentence.'))
"
fi
