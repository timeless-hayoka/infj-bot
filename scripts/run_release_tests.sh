#!/usr/bin/env bash
# Release gate: Kevin-ordered tests + CLI smoke (excludes stress/load suite).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PYTHONNOUSERSITE=1

PY="${ROOT}/.venv/bin/python"
if [[ ! -x "$PY" ]]; then
  echo "Missing venv at ${ROOT}/.venv — run: python -m venv .venv && pip install -e '.[dev]'" >&2
  exit 1
fi

echo "== Phase gate (ordered) =="
"$PY" -m pytest tests/test_roadmap_phases.py -v
"$PY" -m pytest tests/test_pedi.py -v
"$PY" -m pytest tests/test_being_spark.py -v
"$PY" -m pytest tests/test_anchor_cli.py tests/test_anchor_server.py -v

echo "== Full suite (no stress, no live-env) =="
"$PY" -m pytest -q -m "not stress and not env"

echo "== CLI release gate =="
"${ROOT}/scripts/drift" --help >/dev/null
"${ROOT}/scripts/drift" status --json >/dev/null
"$PY" -m drift.interfaces.cli --help >/dev/null
"$PY" -m drift.trinity.reasoning_cycle --help >/dev/null

echo "Release gate: OK"
