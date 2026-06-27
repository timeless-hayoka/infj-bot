#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
source .venv/bin/activate
exec python -m interfaces.cli dashboard
