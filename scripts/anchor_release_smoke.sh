#!/usr/bin/env bash
# Release smoke: dashboard HTTP checks + core API endpoints.
set -euo pipefail
cd "$(dirname "$0")/.."

export PYTHONNOUSERSITE=1
VENV_PY="${VENV_PY:-.venv/bin/python}"
DRIFT="${DRIFT:-./scripts/drift}"

if [[ ! -x "$VENV_PY" ]]; then
  ./scripts/bootstrap_venv.sh
fi

"$VENV_PY" -m pip install -q -e ".[dev]"

ANCHOR_PORT="$(python3 - <<'PY'
import socket
with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
    s.bind(("127.0.0.1", 0))
    print(s.getsockname()[1])
PY
)"
export ANCHOR_PORT

log="$(mktemp)"
pid=""
cleanup() {
  [[ -n "$pid" ]] && kill "$pid" 2>/dev/null || true
  rm -f "$log"
}
trap cleanup EXIT

"$VENV_PY" -m interfaces.cli dashboard --no-open >"$log" 2>&1 &
pid="$!"
sleep 3

python3 - <<PY
import os, time
from urllib.request import urlopen

port = os.environ["ANCHOR_PORT"]
checks = {
    f"http://127.0.0.1:{port}/": "Command Drift",
    f"http://127.0.0.1:{port}/anchor": "Evidence Before Belief",
    f"http://127.0.0.1:{port}/api/health": "ok",
}
for url, marker in checks.items():
    for _ in range(20):
        try:
            with urlopen(url, timeout=5) as resp:
                body = resp.read().decode("utf-8", "replace")
                if marker.lower() not in body.lower():
                    raise SystemExit(f"{url} missing {marker!r}")
                break
        except Exception:
            time.sleep(1)
    else:
        raise SystemExit(f"timeout: {url}")
print("dashboard smoke OK")
PY

"$DRIFT" --help >/dev/null
"$DRIFT" status --json >/dev/null || "$DRIFT" doctor --json >/dev/null
echo "release smoke complete"
