# Web Interface

Two HTTP entrypoints ship with the bot, plus a SocketIO observability stream:

| Entry | Server | File | Default port | Deployed where |
|-------|--------|------|--------------:|----------------|
| **`interfaces/web_app.py`** | Flask + Flask-SocketIO + Gevent | [`interfaces/web_app.py`](../interfaces/web_app.py) | `7860` | Container / Hugging Face Spaces (see [`Dockerfile`](../Dockerfile)) |
| **`interfaces/api.py`** | FastAPI + Uvicorn | [`interfaces/api.py`](../interfaces/api.py) | `8765` | Local dev, scripting |

They expose overlapping but **not identical** routes. Pick the one that matches your deployment:

- The Flask app is the deployable, SocketIO-broadcasting dashboard with the **Observatory** and **PHI Glyph System** views.
- The FastAPI app is the developer-facing surface with SSE streaming, security scanning at the edge, and richer telemetry endpoints (`/api/observer`, `/api/dii*`, `/api/phi`, `/api/hive`, `/api/health`).

This document focuses on the **Flask web app** since it is the production deployment target and was not previously documented.

---

## Run it

### Locally

```bash
python interfaces/web_app.py
# binds 0.0.0.0:7860 (override with PORT)
```

### Container

```bash
docker build -t drift-web .
docker run --rm -p 7860:7860 \
  -e API_KEY=$GEMINI_API_KEY \
  drift-web
```

The Dockerfile’s `CMD` is `python interfaces/web_app.py` and the image exposes port `7860`. Hugging Face Spaces (`sdk: docker` in the repo `README.md` frontmatter) routes incoming traffic to that port.

---

## Routes

### UI

| Path | Method | Purpose |
|------|--------|---------|
| `/` | GET | Main DRIFT dashboard (chat + side panels). |
| `/trial` | GET | Sandbox copy of `/` with a 30-minute scoped session. Returns the same HTML with a synthetic `DRIFT_SESSION_ID` injected so all client requests carry it. |
| `/observatory` | GET | Live cognitive telemetry dashboard (`interfaces/templates/observatory.html`). |
| `/glyph` | GET | PHI Glyph System view (`interfaces/templates/phi_glyph_system.html`). |
| `/phi-glyph` | GET | Alias of `/glyph`. |

The dashboard side-panel includes two buttons that open `/observatory` and `/glyph` in new tabs. If a template file is missing on disk, the route falls back to a developer-laptop path (`/home/crexs/...`) — the canonical location is `interfaces/templates/`.

### Chat API

| Path | Method | Notes |
|------|--------|-------|
| `/api/chat` | POST | DRIFT-native shape `{ "message": str }`. Returns `{ "reply": str }`. Also accepts an Ollama-style `{ "messages": [...], "model": str }` for tools like Reins; in that case the response uses the Ollama `chat` envelope (`{ "model", "created_at", "message": {"role":"assistant","content":str}, "done": true }`). |
| `/v1/chat/completions` | POST, OPTIONS | OpenAI Chat Completions compatibility shim — accepts a `messages: [...]` array and returns an OpenAI-shaped response (`id`, `object`, `created`, `model`, `choices[0].message.content`, `usage`). Token counts are placeholders (0/0/0). |
| `/api/tags` | GET | Ollama `/api/tags`-compatible response advertising a single `infj_bot:latest` model. Lets Ollama clients “discover” the bot. |
| `/api/command` | POST | `{ "command": str, "args": str }`. Routes through `core.commands.handle_command`. Same slash-command surface the CLI uses (`/mode`, `/status`, `/reflect`, `/memory`, `/chain`, `/security`, …). |
| `/api/growth` | GET | Returns the live growth profile (`core.plugins.growth.growth_profile`): stage, XP, progress, avatar, stats. |
| `/api/email` | POST | Stub — returns HTTP 501. No SMTP backend is wired into the Flask app. |

### Trial sandbox semantics

`/trial` issues a fresh `session_id` (uuid4) and stores `time.time()` in an in-memory `trial_sessions` dict. `/api/chat` checks `payload["session_id"]` against `is_trial_active(...)`:

- Session must exist in the dict.
- Session must be **≤ 1800 seconds** old (30 minutes).
- Expired sessions return HTTP 403 with `{"error": "Trial session expired. Please start a new session at /trial"}`.

`trial_sessions` is **process-local memory** — no DB, no cleanup task. Restarting the server drops every active trial. This is intentional for a free-tier sandbox and **not** suitable for paid multi-tenant use.

### Compatibility shims at a glance

The web app speaks three chat dialects so external clients can target it without changes:

| Dialect | Route(s) | Caller examples |
|---------|----------|-----------------|
| DRIFT-native | `POST /api/chat` (`{message}`) | Built-in dashboard JS |
| Ollama | `POST /api/chat` (`{messages, model}`), `GET /api/tags` | Reins, other Ollama UIs |
| OpenAI Chat Completions | `POST /v1/chat/completions` | Any OpenAI SDK pointed at the host |

All three call into `chat_reply(message)`, which builds the prompt via `build_chat_prompt`, runs `brain.agent_turn`, scores it through `evaluate_last`, and persists to `DriftMemory` + `ChatHistory`.

---

## SocketIO: Observatory stream

The Flask app starts a background gevent loop in `broadcast_observatory_state()` that emits `observatory_delta` packets every `broadcast_interval` seconds (default `0.35`s). Delta payloads come from `CognitiveOrchestrator.get_delta_state()`, augmented with a per-tick `network_stats` block:

```json
{
  "network_stats": {
    "raw_kb": <cumulative raw bytes / 1024>,
    "comp_kb": <approx compressed bytes / 1024>,
    "interval_ms": <current broadcast interval>
  },
  "sanctuary": { "location": "...", "anchor_active": true|false },
  "heartbeat": { "bpm": <number> },
  "breath": { "phase": "inhale|exhale", "depth": 0.0-1.0 },
  "phi": { "value": <number> },
  "shadow_radar": { "Tyrant": 0.0-1.0, "Martyr": 0.0-1.0, ... },
  "homeostasis": { "integrity": 0.0-1.0, "growth": 0.0-1.0, ... }
}
```

Only changed keys are sent on each tick (delta-state networking).

### SocketIO events

| Event | Direction | Payload | Behaviour |
|-------|-----------|---------|-----------|
| `latency_ping` | client → server | `{ "timestamp": number }` | Server emits `latency_pong` with `{ "server_time", "client_timestamp" }`. |
| `latency_pong` | server → client | `{ server_time, client_timestamp }` | Client computes RTT, updates the latency card. |
| `auto_adjust_rate` | client → server | `{ "interval": float seconds }` | Server clamps to `[0.2, 1.5]` and updates `broadcast_interval`. Triggered automatically when average RTT > 250ms (slow down) or < 100ms (speed up). |
| `observatory_delta` | server → client | delta object (see above) | Client deep-merges into `localState` and re-renders. |

### Auto-throttling loop

```
client                          server
  │── latency_ping ─────────────►│
  │◄──────────────── latency_pong┤
  │ (compute rolling avg RTT)    │
  │ if avg > 250ms:              │
  │   emit auto_adjust_rate 0.8  │
  │ if avg < 100ms:              │
  │   emit auto_adjust_rate 0.35 │
  │── auto_adjust_rate ──────────►│ (server clamps to [0.2, 1.5])
```

The cumulative `total_bytes_raw` and `total_bytes_compressed` counters approximate compression as `raw_size * 0.3` — this is a UI hint, **not** a precise measurement of `permessage-deflate` output.

---

## Observatory dashboard

`/observatory` renders [`interfaces/templates/observatory.html`](../interfaces/templates/observatory.html). Key cards:

| Card | Source field |
|------|--------------|
| **COMMS LATENCY** | Rolling RTT from `latency_ping/pong`. |
| **COGNITIVE COORDINATES** | `sanctuary.location` + `sanctuary.anchor_active`. |
| **CORE PULSE** | `heartbeat.bpm` — pulse animation period is `60 / bpm`. |
| **RESPIRATION** | `breath.phase` + `breath.depth`. |
| **PHI Ω** | `phi.value` (sparkline keeps last 40 samples). |
| **SHADOW SPECTRUM** | `shadow_radar` keyed by archetype name. |
| **HOMEOSTATIC STABILITY** | 7 needs: integrity, growth, integration, coherence, autonomy, connection, energy. |

The page assumes `Chart.js 4.4.1` and `socket.io 4.7.5` (CDN).

---

## PHI Glyph System

`/glyph` (alias `/phi-glyph`) renders [`interfaces/templates/phi_glyph_system.html`](../interfaces/templates/phi_glyph_system.html). It is a self-contained bundled visualization (the page boots an inline runtime, hence the noscript fallback). Treat the HTML as an opaque asset — edit by replacing the file, not by patching internals.

The dashboard surfaces a `GLYPH SYSTEM` button in the side panel that links here.

---

## Differences vs. the FastAPI app

If you are running [`interfaces/api.py`](../interfaces/api.py) instead, note:

- `api.py` performs `security_defense.scan_input()` **at the API edge** before assembling the prompt; `web_app.py` does not (the scanner still runs inside `build_chat_prompt`).
- `api.py` exposes `POST /api/chat/stream` for SSE token-by-token streaming. `web_app.py` does not stream chat — it streams **telemetry**.
- Additional FastAPI-only routes: `/api/phi`, `/api/hive`, `/api/health`, `/api/dii`, `/api/dii/history`, `/api/observer`, `/api/tools`.
- `api.py` does not implement `/api/tags`, `/v1/chat/completions`, `/trial`, `/observatory`, or `/glyph`.

For Hugging Face Spaces or any single-container deployment, run `web_app.py`. For local development with hot reload, use:

```bash
uvicorn interfaces.api:app --host 127.0.0.1 --port 8765 --reload
```

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| `/observatory` shows empty cards | `CognitiveOrchestrator` not producing deltas (no subsystem state changed yet) | Send a chat message via `/` first; deltas only fire on change. |
| `latency-avg` stuck at `---` | SocketIO connection blocked (CSP, proxy) | Confirm `cdn.socket.io` is reachable; check browser console for handshake errors. |
| Trial session 403 immediately after `/trial` | Server restarted between calls | `trial_sessions` is in-memory only; restart wipes it. Hit `/trial` again. |
| `/glyph` returns blank with no error | Template file resolved to fallback path that does not exist | Confirm `interfaces/templates/phi_glyph_system.html` is present on disk. |
| Ollama client sees no models | Wrong path — Ollama expects `/api/tags` at the root | Point the client at the host root, not a sub-path. |
| OpenAI client gets `0` token counts | Compatibility shim does not compute usage | Expected. The shim returns placeholder usage to satisfy clients that require the field. |

---

## See also

- [HOW_INFJ_BOT_WORKS.md](HOW_INFJ_BOT_WORKS.md) — what happens between `/api/chat` and the response.
- [SUBSYSTEMS.md](SUBSYSTEMS.md) — shadow, hive, retry, triad mechanics that feed the Observatory.
- [HIVE_ROADMAP.md](HIVE_ROADMAP.md) — where the Hive endpoints are heading.
- [`SECURITY.md`](../SECURITY.md) — what to harden before exposing any of these routes publicly.
