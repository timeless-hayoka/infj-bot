# ANCHOR run server

Local-first, single-tenant backend for the ANCHOR console. It runs on the
hunter's own machine, points at their own project, and streams a hunt to the
console's **Live Run** tab over Server-Sent Events. No auth, binds to localhost.

## Install and run

```bash
pip install -r requirements.txt
uvicorn anchor_server:app --host 127.0.0.1 --port 8000
```

On first start it generates an ed25519 signing key at `anchor_signing_key.pem`
and reuses it on later starts, so evidence signatures stay verifiable. The key
is created with owner-only permissions.

## Connect the console

In the console's **Live Run** tab, set the server URL to
`http://127.0.0.1:8000` and click **Connect & run**. The DETECT / CORRELATE /
REPRODUCE tiles climb, the event stream scrolls, and the findings list fills as
events arrive. **Stop run** calls the cancel endpoint and actually terminates
the run.

Note on browsers: a console served over https talking to `http://localhost` is
normally allowed (localhost is a mixed-content exception in Chrome and Firefox).
If your browser blocks it, serve the console over http locally too.

## Two run modes

`POST /runs` accepts a JSON body. Default mode is `demo`.

- **demo** (`{"mode":"demo"}` or no mode): streams a realistic run from built-in
  fixtures, all five tools per specimen. No toolchain required, so the loop
  works immediately.
- **hunt** (`{"mode":"hunt"}`): wraps your real hunt script as a subprocess,
  streams its stdout as `log.line` events, then emits structured case / finding
  / poc events from the registry JSON it writes.

  ```json
  { "mode": "hunt", "script": "trinity_hunt_v4_2_fixed.py", "registry": "registry.json" }
  ```

  This needs slither, mythril, echidna, medusa, and forge installed locally; the
  server only orchestrates and streams. Script and registry paths must stay
  inside the approved project root.

## Live per-stage events from your pipeline

The hunt driver can emit structured events from the final registry, but for true
per-stage live streaming (the ladder climbing as each tool finishes), have the
pipeline stream events as it runs. Drop `anchor_emit.py` next to your pipeline
and call one helper at each stage:

```python
import anchor_emit as ax

ax.case_started(case_id, contract=name, expected=[swc])
ax.stage(case_id, "slither")
if slither_hit:
    ax.detected(case_id, swc=swc, source="slither", severity=sev)
ax.stage(case_id, "mythril")
if tools_agree:
    ax.correlated(case_id, swc=swc, evidence=["slither", "mythril"])
ax.stage(case_id, "forge")
ax.poc_result(case_id, swc=swc, exploit_verified=ok, test_path=path)
ax.case_completed(case_id, "REPRODUCED_REAL" if ok else "CORRELATED")
```

In hunt mode the server launches your pipeline with `ANCHOR_SERVER_URL` and
`ANCHOR_RUN_ID` already set, so the client wires itself with no configuration.
Every call is best-effort and uses only the standard library, so adding these
lines installs nothing and cannot break the pipeline. When the pipeline streams
real ladder events this way, the server skips its registry replay so nothing is
duplicated. Do not call `run_started` or `run_completed` under the server; it
brackets the run for you. Running the pipeline standalone instead? Call
`ax.start_run()` once to create a run, then connect the console to that run id.

## Event envelope

Every event uses the versioned envelope the console consumes:

```json
{
  "schema_version": "1.0",
  "event_id": "evt_run_xxx_000007",
  "run_id": "run_xxx",
  "type": "finding.correlated",
  "timestamp": "2026-06-25T00:00:00+00:00",
  "payload": { }
}
```

Types: `run.started`, `case.started`, `stage.started`, `finding.detected`,
`finding.correlated`, `poc.result`, `case.completed`, `run.completed`,
`run.stopped`, `log.line`.

## Event replay

The stream keeps an append-only event log per run. Clients can reconnect with
`GET /runs/{id}/events?after={event_id}` to replay missed events and then follow
new ones live. That makes a reconnecting browser tab trustworthy instead of
racing a shared queue.

## Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| GET  | `/` | health, version, server public key |
| GET  | `/pubkey` | ed25519 public key for verifying evidence |
| POST | `/runs` | start a run, returns `{run_id}` |
| GET  | `/runs/{id}/events` | SSE event stream |
| POST | `/runs/{id}/ingest` | push a real event from the pipeline |
| POST | `/runs/{id}/cancel` | cancel the run, emit `run.stopped` |
| GET  | `/runs/{id}/registry` | final registry JSON |
| GET  | `/cases/{id}` | case detail for the drawer |
| POST | `/evidence/sign` | sign an evidence bundle with the server key |

## Evidence signing

The console's evidence bundle ships with a `PENDING_SERVER_SIGNATURE` placeholder
and a real SHA-256 digest. POST that bundle to `/evidence/sign` and the server
returns it with a real ed25519 signature plus its public key. Anyone can verify
the signature against `/pubkey`, which makes a bundle tamper-evident and
locally signed rather than just hashed.

## Production notes

This is built for a single hunter on localhost. Before exposing it anywhere:
add auth, tighten CORS from `*` to your origin, keep run script and registry
paths under an approved project root, and persist runs if you need restart
resilience.
