#!/usr/bin/env bash
# DRIFT Continuous Mode Launcher
# Sets up Python path correctly for infj_bot imports

set -euo pipefail
cd "$(dirname "$0")"
export PYTHONPATH="/home/crexs:/home/crexs/infj_bot/core:$PYTHONPATH"
source venv/bin/activate
exec python main.py
