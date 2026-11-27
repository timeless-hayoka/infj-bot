#!/usr/bin/env bash
set -euo pipefail
umask 077
work="$RUNNER_TEMP/drift-tunnel-trial"
image="drift-tunnel-trial:ci"
case "${1:-}" in
preflight)
    mkdir -p "$work"
    curl --fail --silent --show-error --location --retry 2 \
      https://github.com/openai/tunnel-client/releases/download/v0.0.21/tunnel-client-v0.0.21-linux-amd64.zip \
      --output "$work/client.zip"
    echo "9e91a539e3ae1c436d499f216a1d7514b3c86cc7779032f41b2a05821d74b03a  $work/client.zip" | sha256sum --check
    unzip -q -o "$work/client.zip" -d "$work"
    client="$(find "$work" -type f -name tunnel-client -print -quit)"
    test -n "$client"
    chmod 700 "$client"
    "$client" --version
    "$client" help quickstart >/dev/null
    "$client" run --help >/dev/null
    docker build -t "$image" .
    bash scripts/compose_adapter_smoke.sh "$image"
    ;;
live)
    test -n "${CONTROL_PLANE_API_KEY:-}" || { echo "Missing restricted runtime key"; exit 1; }
    [[ "${CONTROL_PLANE_TUNNEL_ID:-}" =~ ^tunnel_[a-f0-9]{32}$ ]] || { echo "Missing or invalid tunnel ID"; exit 1; }
    client="$(find "$work" -type f -name tunnel-client -print -quit)"
    test -x "$client"
    export DRIFT_PLUGIN_TOKEN="$(openssl rand -hex 32)"
    export DRIFT_VAULT_SECRET="$(openssl rand -hex 32)"
    export DRIFT_IMAGE="$image" DRIFT_PORT=18080
    export COMPOSE_PROJECT_NAME="drift-tunnel-${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}"
    pid=""
    cleanup() {
        if [ -n "$pid" ]; then kill "$pid" 2>/dev/null || true; wait "$pid" 2>/dev/null || true; fi
        docker compose down --volumes --remove-orphans >/dev/null 2>&1 || true
    }
    trap cleanup EXIT
    docker compose up -d --no-build
    cid="$(docker compose ps -q drift-core)"
    test -n "$cid"
    for i in $(seq 1 60); do
        if curl --silent --fail -H "Authorization: Bearer $DRIFT_PLUGIN_TOKEN" http://127.0.0.1:18080/health >/dev/null; then break; fi
        test "$i" -lt 60 || exit 1
        sleep 1
    done
    # The child inherits only the container's disposable adapter credentials.
    command="docker exec -i -e DRIFT_MCP_MEMORY_READ=0 $cid python -m drift.core.private_mcp"
    "$client" run --mcp-command "$command" --health.listen-addr 127.0.0.1:18081 >"$work/runtime.log" 2>&1 &
    pid=$!
    for i in $(seq 1 60); do
        kill -0 "$pid" || { echo "Tunnel client exited before readiness"; exit 1; }
        if curl --silent --fail http://127.0.0.1:18081/readyz >/dev/null; then break; fi
        test "$i" -lt 60 || { echo "Tunnel readiness not established"; exit 1; }
        sleep 1
    done
    echo "Tunnel client readiness observed; health-only private trial available for up to 10 minutes."
    for i in $(seq 1 120); do
        kill -0 "$pid" || { echo "Tunnel process stopped unexpectedly"; exit 1; }
        curl --silent --fail http://127.0.0.1:18081/readyz >/dev/null || exit 1
        sleep 5
    done
    echo "Bounded trial window ended. No user memory was mounted."
    ;;
*) exit 2;;
esac
