# Private DRIFT adapter (Docker Compose)

This configuration runs the actual read-only HTTP adapter, not the general-purpose MCP bridge or a public inference service. It binds port 8000 to loopback only and keeps application state in the named `drift-state` Docker volume. No Google Cloud, SQL proxy, or removable-drive paths are needed.

Before starting, supply `DRIFT_PLUGIN_TOKEN` and `DRIFT_VAULT_SECRET` via a private environment or an untracked, access-restricted environment file. Generate strong values locally and keep the vault secret stable across restarts. Never put either value into the browser, frontend bundle, or Git.

```sh
docker compose config --quiet
docker compose up -d --build
docker compose ps
```

The adapter provides authenticated `GET /health` and `POST /memory/search`. It does not provide live chat or telemetry yet. Keep the token server-side; a future authenticated proxy can connect a reviewed UI to it.

`docker compose down` stops the service while retaining the named volume. Do not use `down --volumes` on a real installation. Existing host memory is not automatically migrated; back up and explicitly review any migration. Do not expose port 8000 to the public Internet.

CI uses a disposable Compose project with fresh credentials and a separate volume to test real HTTP authentication and memory recall after container recreation. Its cleanup deletes only that disposable volume. The standard image entrypoint remains unchanged.
