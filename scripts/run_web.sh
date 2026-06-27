#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
source .venv/bin/activate
HOST="${ANCHOR_WEB_HOST:-127.0.0.1}"
PORT="${ANCHOR_PORT:-8765}"
exec uvicorn interfaces.api:app --host "$HOST" --port "$PORT" --reload
