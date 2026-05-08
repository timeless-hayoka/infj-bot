#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

stamp="$(date +%Y%m%d-%H%M%S)"
out="${1:-$HOME/infj_bot-backup-$stamp.tar.gz}"

tar \
  --exclude='venv' \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  --exclude='.env' \
  -czf "$out" \
  .

echo "backup=$out"
echo "NOTE: .env excluded. Transfer API_KEY separately."
