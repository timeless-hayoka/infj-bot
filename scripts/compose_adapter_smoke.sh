#!/usr/bin/env bash
set -euo pipefail
export DRIFT_IMAGE="${1:?usage: compose_adapter_smoke.sh IMAGE}"
# This project and its credentials are disposable, never use a user's state volume.
export COMPOSE_PROJECT_NAME="drift-ci-${GITHUB_RUN_ID:-$$}-${GITHUB_RUN_ATTEMPT:-1}"
export DRIFT_PLUGIN_TOKEN="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
export DRIFT_VAULT_SECRET="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
export DRIFT_PORT=18080
cleanup() {
    docker compose logs --no-color || true
    docker compose down --volumes --remove-orphans >/dev/null || true
}
trap cleanup EXIT
docker compose config --quiet
docker compose up -d --no-build
wait_ready() {
    docker compose exec -T drift-core python - <<'PY'
import os
import time
import urllib.request
import urllib.error

url = "http://127.0.0.1:8000/health"
token = os.environ["DRIFT_PLUGIN_TOKEN"]
for attempt in range(60):
    try:
        req = urllib.request.Request(url, headers={"Authorization": "Bearer " + token})
        with urllib.request.urlopen(req, timeout=2) as response:
            assert response.status == 200
        break
    except (OSError, urllib.error.URLError):
        if attempt == 59:
            raise
        time.sleep(1)
try:
    urllib.request.urlopen(url, timeout=2)
except urllib.error.HTTPError as error:
    assert error.code == 401
else:
    raise AssertionError("Unauthenticated health request was accepted")
PY
}
wait_ready
first="$(docker compose ps -q drift-core)"
marker="compose-restart-$(python3 -c 'import uuid; print(uuid.uuid4().hex[:12])')"
docker compose exec -T -e SMOKE_MARKER="$marker" drift-core python - <<'PY'
import os
from drift.core.mcp_server import get_memory

memory = get_memory()
memory.save_interaction_sync("Persistent marker " + os.environ["SMOKE_MARKER"], "Durable test record")
PY
docker compose down
docker compose up -d --no-build
wait_ready
second="$(docker compose ps -q drift-core)"
test -n "$first" && test -n "$second" && test "$first" != "$second"
docker compose exec -T -e SMOKE_MARKER="$marker" drift-core python - <<'PY'
import json
import os
import urllib.request
import urllib.error

url = "http://127.0.0.1:8000/memory/search"
marker = os.environ["SMOKE_MARKER"]
payload = json.dumps({"query": "Persistent marker " + marker, "limit": 5}).encode()
headers = {"Content-Type": "application/json"}
try:
    urllib.request.urlopen(urllib.request.Request(url, data=payload, headers=headers), timeout=10)
except urllib.error.HTTPError as error:
    assert error.code == 401
else:
    raise AssertionError("Unauthenticated memory access was accepted")
headers["Authorization"] = "Bearer " + os.environ["DRIFT_PLUGIN_TOKEN"]
with urllib.request.urlopen(urllib.request.Request(url, data=payload, headers=headers), timeout=30) as response:
    assert response.status == 200
    assert marker in json.load(response)["result"]
print("Authenticated HTTP recall survived container recreation with persistent volume")
PY
printf 'Distinct container IDs: %s -> %s\n' "$first" "$second"
docker compose exec -T -e SMOKE_MARKER="$marker" drift-core python tests/private_mcp_probe.py
