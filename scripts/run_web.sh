#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
source venv/bin/activate
exec uvicorn api:app --host 127.0.0.1 --port 8765 --reload
