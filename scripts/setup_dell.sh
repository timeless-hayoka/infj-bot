#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"

test -f .env || { echo "Missing .env. Copy .env.example to .env and set API_KEY."; exit 1; }
test -d chroma_db || { echo "Missing chroma_db memory directory."; exit 1; }

python - <<'PY'
from dotenv import load_dotenv
import os
load_dotenv()
assert os.getenv("API_KEY"), "API_KEY missing"
from memory import DriftMemory
m = DriftMemory()
print(f"memory_count={m.collection.count()}")
PY
