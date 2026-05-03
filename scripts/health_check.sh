#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
source venv/bin/activate

python -m py_compile main.py brain.py memory.py commands.py bug_ops.py emotion.py cognition.py growth.py prompt_builder.py guardrails.py history.py web_app.py api.py mcp_server.py voice.py seed_cognition.py stress_test.py
python stress_test.py --requests 10 --workers 2
python - <<'PY'
from memory import InfjMemory
m = InfjMemory()
print("chroma_collection=infj_companion_memories")
print(f"memory_count={m.collection.count()}")
assert m.collection.count() > 0, "Chroma memory is empty"
PY

if [[ "${LIVE_API_CHECK:-0}" == "1" ]]; then
  python - <<'PY'
from brain import InfjBrain
print(InfjBrain().think("Health check: answer in one short sentence."))
PY
fi
