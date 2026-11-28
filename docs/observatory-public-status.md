# Observatory public status

The public interface is a static demonstration plus a narrow same-origin GET /api/status function. It never accepts a target URL, never forwards arbitrary requests, and never exposes memory or inference. The only upstream is the authenticated adapter /health endpoint.

For a reviewed preview deployment, configure DRIFT_BACKEND_ORIGIN as the HTTPS origin of the privately administered adapter gateway, and DRIFT_PLUGIN_TOKEN as a server-side secret. Never put the token in client code or build output. Restrict the upstream gateway to authenticated requests, TLS, and appropriate rate limits. No public upstream or credentials are provisioned by this branch.

When configuration is missing, invalid, or the authenticated adapter is unreachable, the endpoint returns HTTP 503 with status offline. A ready result only means the existing adapter health check succeeded, not that live model inference or memory retrieval was performed. The page continues to label its scripted responses as demonstrations.

Unit checks: node --test tests/observatory-status.test.mjs
The opt-in integration test requires DRIFT_STATUS_INTEGRATION=1 and a real authorized HTTPS adapter; do not claim it passed unless executed.
