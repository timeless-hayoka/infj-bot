#!/usr/bin/env bash
# Open DRIFT interactive chat in a real terminal (TTY required).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

run_chat() {
  cd "$ROOT"
  set -a
  # shellcheck source=/dev/null
  [[ -f "$ROOT/.env" ]] && source "$ROOT/.env"
  # shellcheck source=/dev/null
  [[ -f "$HOME/.drift_os/config/storage.env" ]] && source "$HOME/.drift_os/config/storage.env"
  set +a
  export DRIFT_CHAT_NO_SPAWN=1
  exec "$ROOT/scripts/drift" chat
}

if [[ -t 0 && -t 1 ]]; then
  run_chat
fi

if [[ "${DRIFT_CHAT_NO_SPAWN:-}" == "1" ]]; then
  echo "DRIFT chat needs an interactive terminal (stdin is not a TTY)." >&2
  echo "Run: cd $ROOT && ./scripts/drift chat" >&2
  exit 1
fi

REMOTE="cd $(printf '%q' "$ROOT") && set -a && source .env 2>/dev/null; source \"\$HOME/.drift_os/config/storage.env\" 2>/dev/null; set +a && export DRIFT_CHAT_NO_SPAWN=1 && exec ./scripts/drift chat"

if command -v gnome-terminal >/dev/null 2>&1; then
  exec gnome-terminal --title="DRIFT Chat" -- bash -lc "$REMOTE"
fi
if command -v xfce4-terminal >/dev/null 2>&1; then
  exec xfce4-terminal --title="DRIFT Chat" -e bash -lc "$REMOTE"
fi
if command -v konsole >/dev/null 2>&1; then
  exec konsole --new-tab -p tabtitle="DRIFT Chat" -e bash -lc "$REMOTE"
fi
if command -v x-terminal-emulator >/dev/null 2>&1; then
  exec x-terminal-emulator -T "DRIFT Chat" -e bash -lc "$REMOTE"
fi

echo "No terminal emulator found." >&2
echo "Open a terminal and run: cd $ROOT && ./scripts/drift chat" >&2
exit 1
