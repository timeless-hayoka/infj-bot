#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

./scripts/bootstrap_venv.sh

PYTHON_BIN="${PYTHON_BIN:-python3}"
VENV_DIR="${VENV_DIR:-.venv}"
VENV_PY="$VENV_DIR/bin/python"

"$VENV_PY" -m interfaces.cli setup
"$VENV_PY" -m interfaces.cli doctor --json
"$VENV_PY" -m interfaces.cli status --json
"$VENV_PY" -m interfaces.cli release --json
"$VENV_PY" -m pytest -q tests/test_trinity_caseflow.py tests/test_sync_logs.py

ANCHOR_PORT="$(python3 - <<'ANCHOR_PORT_PY'
import socket
with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
    sock.bind(("127.0.0.1", 0))
    print(sock.getsockname()[1])
ANCHOR_PORT_PY
)"
export ANCHOR_PORT

dashboard_log="$(mktemp)"
dashboard_pid=""
cleanup() {
    if [[ -n "$dashboard_pid" ]] && kill -0 "$dashboard_pid" 2>/dev/null; then
        kill "$dashboard_pid" 2>/dev/null || true
    fi
    rm -f "$dashboard_log"
}
trap cleanup EXIT

"$VENV_PY" -m interfaces.cli dashboard --no-open >"$dashboard_log" 2>&1
dashboard_pid="$(sed -n 's/.*(pid \([0-9][0-9]*\)).*/\1/p' "$dashboard_log" | tail -n1)"
if [[ -z "$dashboard_pid" ]]; then
    cat "$dashboard_log"
    exit 1
fi
python3 - <<'ANCHOR_PY'
from urllib.error import URLError
from urllib.request import urlopen
import os
import time

port = os.environ['ANCHOR_PORT']
checks = {
    f'http://127.0.0.1:{port}/': 'Command Drift',
    f'http://127.0.0.1:{port}/anchor': 'Evidence Before Belief',
}
for url, marker in checks.items():
    last_error = None
    for _ in range(30):
        try:
            with urlopen(url, timeout=10) as response:
                body = response.read().decode('utf-8', 'replace')
                if marker not in body:
                    raise SystemExit(f'{url} missing {marker!r}')
                break
        except URLError as exc:
            last_error = exc
            time.sleep(2)
    else:
        raise SystemExit(f'{url} unavailable after retries: {last_error}')
ANCHOR_PY

cleanup
trap - EXIT

echo "ANCHOR bootstrap complete."
echo "Next: anchor dashboard"
