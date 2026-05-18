#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

# Activate virtual environment if present
if [[ -f venv/bin/activate ]]; then
    source venv/bin/activate
fi

echo "=== DRIFT Health Check ==="
python3 selfcheck.py --verbose "$@"

if [[ "${LIVE_API_CHECK:-0}" == "1" ]]; then
    echo ""
    echo "=== Live API Check ==="
    python3 -c "
from infj_bot.core.brain import DriftBrain
print(DriftBrain().think('Health check: answer in one short sentence.'))
"
fi
