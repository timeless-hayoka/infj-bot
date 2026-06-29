#!/usr/bin/env bash
# Apply smooth-run defaults for DRIFT on CPU / limited RAM. Safe to re-run.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

warn() { echo -e "${YELLOW}⚠${NC} $*"; }
ok() { echo -e "${GREEN}✓${NC} $*"; }
bad() { echo -e "${RED}✗${NC} $*"; }

echo "=== DRIFT smooth-run setup ==="

# 1. Env file
if [[ ! -f "$ROOT/.env" ]]; then
  cp "$ROOT/.env.performance" "$ROOT/.env"
  ok "Created .env from .env.performance"
else
  warn ".env already exists — merge keys from .env.performance manually if needed"
fi

# 2. Ollama tuning (system service)
OLLAMA_DROPIN="/etc/systemd/system/ollama.service.d/smooth.conf"
if [[ -w /etc/systemd/system/ollama.service.d ]] 2>/dev/null || sudo -n true 2>/dev/null; then
  sudo mkdir -p /etc/systemd/system/ollama.service.d
  sudo tee "$OLLAMA_DROPIN" >/dev/null <<'EOF'
[Service]
Environment=OLLAMA_NUM_PARALLEL=1
Environment=OLLAMA_MAX_LOADED_MODELS=1
Environment=OLLAMA_KEEP_ALIVE=5m
EOF
  sudo systemctl daemon-reload
  sudo systemctl restart ollama
  ok "Ollama tuned (1 parallel, 1 model, 5m keep-alive)"
else
  warn "Could not write Ollama systemd drop-in — add these to your shell or service:"
  echo "  export OLLAMA_NUM_PARALLEL=1 OLLAMA_MAX_LOADED_MODELS=1 OLLAMA_KEEP_ALIVE=5m"
fi

# 3. Ensure small model is present
if command -v ollama >/dev/null 2>&1; then
  if ! ollama list 2>/dev/null | grep -q 'qwen2.5:1.5b'; then
    warn "Pulling qwen2.5:1.5b (recommended for 14GB RAM)..."
    ollama pull qwen2.5:1.5b
  else
    ok "qwen2.5:1.5b already installed"
  fi
else
  warn "ollama not in PATH"
fi

# 4. Health checks
SWAP_USED=$(free | awk '/Swap/{print $3}')
SWAP_TOTAL=$(free | awk '/Swap/{print $2}')
if [[ "$SWAP_TOTAL" -gt 0 ]]; then
  PCT=$((SWAP_USED * 100 / SWAP_TOTAL))
  if [[ "$PCT" -gt 80 ]]; then
    bad "Swap ${PCT}% full — close heavy apps (Chrome, old drift web) or add swap"
    echo "  Top memory: ps aux --sort=-%mem | head -8"
  else
    ok "Swap usage OK (${PCT}%)"
  fi
fi

DISK_PCT=$(df "$ROOT" | awk 'NR==2 {gsub(/%/,"",$5); print $5}')
if [[ "$DISK_PCT" -gt 90 ]]; then
  bad "Disk ${DISK_PCT}% full — free space or models/tests will stutter"
else
  ok "Disk usage OK (${DISK_PCT}%)"
fi

# 5. Restart drift web if running (optional)
API_PID=$(pgrep -f 'uvicorn drift.interfaces.api' 2>/dev/null | head -1 || true)
if [[ -n "$API_PID" ]]; then
  warn "DRIFT API running (pid $API_PID) — restart to pick up .env:"
  echo "  kill $API_PID && cd $ROOT && set -a && source .env && set +a && .venv/bin/python -m uvicorn drift.interfaces.api:app --host 127.0.0.1 --port 8765"
fi

echo
ok "Done. Start chat:  cd $ROOT && ./scripts/drift ask 'hello'"
echo "  Or web UI:       ./scripts/drift web"
echo "  Verify Ollama:   ollama run qwen2.5:1.5b 'say hi in one line'"
