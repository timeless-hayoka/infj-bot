# Web Interface Reference

This document describes `interfaces/web_app.py`, the **deployed** surface of
PHI // DRIFT. It is a Flask + Flask-SocketIO app running on a Gevent worker
that serves three things from a single process:

1. The chat UI at `/` (and a sandboxed variant at `/trial`).
2. Two operator dashboards: `/observatory` and `/glyph`.
3. Chat APIs in three flavors: native, OpenAI-compatible, and
   Ollama-compatible.

For deployment specifics see [`DEPLOYMENT.md`](DEPLOYMENT.md). For the
architecture behind a chat turn see
[`HOW_INFJ_BOT_WORKS.md`](HOW_INFJ_BOT_WORKS.md).

---

## 1. Runtime topology

```
                           ┌──────────────────────────┐
                           │ interfaces/web_app.py    │
                           │  (gevent + monkey patch) │
                           └──────────────┬───────────┘
                                          │
   ┌──────────────────────────────────────┼──────────────────────────────────┐
   │                                      │                                  │
   ▼                                      ▼                                  ▼
 Flask routes                       SocketIO server                  Background thread
 (chat UI, dashboards,              (observatory_delta,              broadcast_observatory_state()
  REST endpoints)                    latency_ping, etc.)             every `broadcast_interval` sec
```

Process startup:

- `gevent.monkey.patch_all()` runs **before** any other import. This is
  required for the SocketIO async mode and must stay at the very top of the
  file.
- `DriftBrain`, `DriftMemory`, `ChatHistory`, `BotState`, `GoalsDB`,
  `DocumentStore`, and a `CognitiveOrchestrator` are constructed once at
  import time and reused across requests.
- A daemon thread starts `broadcast_observatory_state()`, which polls
  `CognitiveOrchestrator.get_delta_state()` and emits an
  `observatory_delta` event over SocketIO whenever there is a change.

The server listens on `0.0.0.0:${PORT:-7860}`.

---

## 2. HTTP routes

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/` | Chat UI (`INDEX_HTML`) |
| GET | `/trial` | Same UI with a 30-minute sandbox session injected |
| GET | `/observatory` | Renders `interfaces/templates/observatory.html` |
| GET | `/glyph`, `/phi-glyph` | Renders `interfaces/templates/phi_glyph_system.html` |
| GET | `/api/growth` | Returns the JSON growth profile for the side panel |
| GET | `/api/tags` | Ollama-compatible model list (for Reins, Open WebUI, etc.) |
| POST | `/api/chat` | Native chat endpoint (also accepts Ollama-style payloads) |
| POST | `/api/command` | Slash-command dispatcher (`/mode`, `/status`, `/memory`, …) |
| POST | `/api/email` | Stubbed; always returns 501 |
| POST, OPTIONS | `/v1/chat/completions` | OpenAI-compatible chat completion |

### 2.1 `/api/chat`

Accepts two payload shapes, dispatched by the presence of `messages`:

**Native shape** — used by the bundled UI:

```json
POST /api/chat
{ "message": "hi", "session_id": "optional-uuid-from-/trial" }
```

```json
200 OK
{ "reply": "..." }
```

**Ollama-compatible shape** — used by external Ollama clients (Reins,
LangChain's `ChatOllama`, etc.):

```json
POST /api/chat
{
  "model": "infj_bot:latest",
  "messages": [
    { "role": "user", "content": "hi" }
  ]
}
```

```json
200 OK
{
  "model": "infj_bot:latest",
  "created_at": "2026-05-26T21:00:00.000Z",
  "message": { "role": "assistant", "content": "..." },
  "done": true
}
```

The dispatcher only looks at the last `role: "user"` message — earlier turns
in the array are ignored. Conversation continuity is provided by
`DriftMemory` and `ChatHistory` server-side, not by the client-sent
`messages` array.

### 2.2 `/v1/chat/completions`

OpenAI-compatible — works with any client that targets
`/v1/chat/completions` (the LangChain `ChatOpenAI` adapter, LiteLLM, the
official `openai` SDK with a custom `base_url`, etc.):

```json
POST /v1/chat/completions
{
  "model": "infj_bot",
  "messages": [
    { "role": "user", "content": "hello" }
  ]
}
```

The response uses the standard OpenAI envelope (`choices[0].message`,
`finish_reason: "stop"`, `usage` zeroed out). Streaming is **not**
implemented — the response is always a single non-streaming completion.

### 2.3 `/api/command`

Dispatches to `core.commands.handle_command(...)`. Payload:

```json
POST /api/command
{ "command": "mode", "args": "engineer" }
```

Returns `{ "reply": "<command output>" }`. Supported commands are listed in
the project [`README`](../README.md#commands).

### 2.4 `/api/tags`

Returns a fixed Ollama-style model catalog containing a single fake
`infj_bot:latest` entry. The purpose is **not** to expose real Ollama
metadata — it lets clients that probe `/api/tags` before chatting (Reins,
some Open WebUI versions) discover that the endpoint exists and select the
model.

### 2.5 `/trial`

`GET /trial` mints a 30-minute sandbox session by:

1. Generating a UUID and storing it in the in-memory `trial_sessions` dict
   with the current timestamp.
2. Returning the chat UI with a small JavaScript shim that:
   - Defines `DRIFT_SESSION_ID = "<uuid>"`.
   - Auto-attaches `session_id` to every `POST` body.

`is_trial_active(session_id)` then gates `POST /api/chat`: if a
`session_id` is present and older than 1800 seconds (or unknown), the
endpoint returns HTTP 403 with `{"error": "Trial session expired. ..."}`.

Sessions live in process memory — restart wipes them. Sessions are not
cleaned up proactively; the dict grows for the lifetime of the process.

### 2.6 `/observatory` and `/glyph`

These routes read the corresponding HTML file from
`interfaces/templates/` and render it through `render_template_string`.
They fall back to legacy paths under `/home/crexs/` if the template is
missing from the package — useful for the original development host, but
**not** something you should rely on in deployed environments. Always ship
the templates inside the image.

---

## 3. WebSocket / SocketIO

The SocketIO server uses `async_mode="gevent"`, accepts all origins
(`cors_allowed_origins="*"`), and enables `permessage-deflate` compression.

### 3.1 Events emitted by the server

| Event | Payload | Cadence |
|-------|---------|---------|
| `observatory_delta` | Changed fields of `CognitiveOrchestrator.get_delta_state()` plus `timestamp` and a `network_stats` block (`raw_kb`, `comp_kb`, `interval_ms`) | Every `broadcast_interval` seconds (default 0.35 s, clamped to [0.2, 1.5]) |
| `latency_pong` | `{ server_time, client_timestamp }` | In response to `latency_ping` |

The broadcaster only emits when there is at least one changed field
(`len(delta) > 1`, accounting for the always-present `timestamp` key). This
is the "delta-state networking" pattern documented in
[`DRIFT_UPGRADE_MAY_2024.md`](DRIFT_UPGRADE_MAY_2024.md).

### 3.2 Events accepted from the client

| Event | Payload | Effect |
|-------|---------|--------|
| `latency_ping` | `{ timestamp: <client_unix_ms> }` | Replies with `latency_pong` so the client can compute RTT |
| `auto_adjust_rate` | `{ interval: <seconds> }` | Sets `broadcast_interval` server-side; clamped to `[0.2, 1.5]` |

The recommended client behavior — used by the Observatory dashboard — is to
sample RTT once per second and call `auto_adjust_rate` whenever average
latency drifts outside the 100–250 ms target band. Above 250 ms slow the
stream; below 100 ms speed it up.

---

## 4. Background broadcaster

`broadcast_observatory_state()` runs in a daemon thread (started under
`threading.Thread`, but cooperates via `gevent.sleep`). Each tick:

1. Calls `cognitive_orchestrator.get_delta_state()` to get the dict of
   fields that have changed since the last broadcast.
2. If anything changed, computes a synthetic `network_stats` payload:
   - `raw_kb` — running total of raw JSON bytes broadcast.
   - `comp_kb` — running total estimated **as 30 % of raw** (not the actual
     compressed bytes; this is a heuristic for the dashboard).
   - `interval_ms` — current broadcast interval in milliseconds.
3. Emits `observatory_delta` with the delta + the synthetic stats.
4. Sleeps `broadcast_interval` seconds.

Exceptions during a tick are swallowed silently. If the dashboard goes
quiet, attach a logger or check that
`CognitiveOrchestrator.get_delta_state()` is returning data.

---

## 5. Configuration

The app reads three environment variables of its own and inherits the rest
from `core/config.py`:

| Variable | Default | Effect |
|----------|---------|--------|
| `PORT` | `7860` | Bind port for the SocketIO server |
| `INFJ_DATA_DIR` | unset (project-relative) | Where Chroma / SQLite live (see `config_adapter.py`) |
| `STRONG_CONTINUOUS_MODE` | `true` | Enables background drift cycles inside `CognitiveOrchestrator` |

`SECRET_KEY` is hard-coded to `"drift-secret-key"`. Override it before
exposing the app on a public URL where Flask session cookies matter; the
current routes do not use sessions, but plugins that add login flows will.

Other knobs (model routing, prompt budgets, memory limits, security
defense) live in `core/config.py` and are described in
[`HOW_INFJ_BOT_WORKS.md`](HOW_INFJ_BOT_WORKS.md#9-configuration--portability).

---

## 6. Constraints and known limits

- **No streaming** on either chat endpoint — every reply is a single,
  non-chunked JSON response. Clients that expect token streaming will
  block until the full reply is ready.
- **No auth.** Anyone who can reach the port can chat, list models, and
  open the dashboards. Put it behind your own gateway if you expose it on
  the public internet.
- **Trial sessions are memory-only.** Restarts forget every active trial
  session, and the in-memory dict never shrinks.
- **OpenAI usage block is always zero** — `prompt_tokens`,
  `completion_tokens`, and `total_tokens` are all `0` in the response. The
  bot does not currently surface real token counts to OpenAI clients.
- **`/api/email`** is a stub and returns HTTP 501. There is no SMTP
  integration in the deployed image.
- **Observatory compression metric is synthetic.** The `comp_kb` figure is
  `raw_kb × 0.3`, not measured compressed bytes. Use it as a relative
  trend, not as a hard SLO.
- **`SECRET_KEY` is hard-coded.** Replace it before relying on Flask
  sessions or signed cookies.

---

## 7. See also

- [`DEPLOYMENT.md`](DEPLOYMENT.md) — packaging, Hugging Face Spaces
  frontmatter, secrets.
- [`HOW_INFJ_BOT_WORKS.md`](HOW_INFJ_BOT_WORKS.md) — what
  `CognitiveOrchestrator.assemble_prompt()` does between
  `/api/chat` arriving and the reply being saved.
- [`DRIFT_UPGRADE_MAY_2024.md`](DRIFT_UPGRADE_MAY_2024.md) — original
  rationale for delta-state networking, auto-throttling, and the
  Gevent + SocketIO stack.
- `interfaces/api.py` — a separate FastAPI + SSE surface used for internal
  streaming experiments. Not the production deployment.
