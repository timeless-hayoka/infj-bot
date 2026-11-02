#!/usr/bin/env bash
set -euo pipefail
image="${1:?usage: docker_smoke.sh IMAGE}"
container_id=$(docker run -d --network none \
    -e DRIFT_OS_ROOT=/tmp/drift-container-smoke \
    -e DRIFT_USE_LOCAL_EMBEDDINGS=true "$image")
cleanup() {
    docker logs "$container_id" || true
    docker rm -f "$container_id" >/dev/null || true
}
trap cleanup EXIT
# Execute inside the container: no published ports, credentials, or outbound network.
docker exec "$container_id" python -c '
import time, urllib.request, json
for attempt in range(60):
    try:
        with urllib.request.urlopen("http://127.0.0.1:8000/api/health", timeout=2) as r:
            payload=json.load(r)
            assert r.status == 200 and payload["ok"] is True
        break
    except Exception:
        if attempt == 59:
            raise
        time.sleep(1)
from drift.interfaces import api
assert api.DriftBrain.__module__ == "drift.core.brain", "degraded core imports"
assert api._get_memory() is not None, "memory unavailable"
print("Default container command serves a healthy API on port 8000; core and memory loaded")
'
