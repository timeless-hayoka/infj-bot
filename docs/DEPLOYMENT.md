# Deployment

This page covers how to run DRIFT outside of `python interfaces/main.py` on a developer laptop — Docker locally, Hugging Face Spaces, and the routes/ports the web image actually exposes.

For day-to-day development setup see the [root README](../README.md#getting-started). For local CLI-only operation no deployment is needed — `python interfaces/main.py` is sufficient.

---

## Web entrypoint

The deployable entrypoint is **`interfaces/web_app.py`**, a Flask + Flask-SocketIO app run on **gevent**. It is the canonical surface for Hugging Face Spaces, Docker, and any reverse-proxied install.

Key facts:

| Thing | Value |
|-------|-------|
| Entry script | `python interfaces/web_app.py` |
| Port | `${PORT}` → defaults to **7860** (HF Spaces convention) |
| Server | `flask_socketio.SocketIO` + `gevent` async mode |
| WebSocket compression | `permessage-deflate` enabled |
| Broadcast loop | `broadcast_observatory_state` thread, 0.2 – 1.5 s interval (auto-throttled) |

The legacy REST-only API (`interfaces/api.py`, uvicorn on `127.0.0.1:8765`) is still available for headless installs but is not what the Dockerfile boots.

---

## HTTP routes

| Route | Method | Purpose |
|-------|--------|---------|
| `/`                        | GET  | Main HTML dashboard |
| `/trial`                   | GET  | 30-minute trial session (injects a per-session UUID into the page) |
| `/observatory`             | GET  | Real-time cognitive observatory (consumes the SocketIO stream) |
| `/glyph` / `/phi-glyph`    | GET  | PHI Glyph System dashboard |
| `/api/chat`                | POST | Single-turn chat. Accepts both the native `{message}` form and an Ollama-compatible `{messages: [...]}` body. |
| `/api/command`             | POST | Run a slash command (`{command, args}`) |
| `/api/growth`              | GET  | Bio-growth profile snapshot |
| `/api/email`               | POST | Stub — returns `501 Not Implemented` (no backend wired) |
| `/api/tags`                | GET  | Ollama-compatible model list (single model: `infj_bot:latest`) |
| `/v1/chat/completions`     | POST | OpenAI-compatible chat completions shim |
| `/` SocketIO `observatory_delta` | — | Server → client telemetry deltas |
| `/` SocketIO `latency_ping` / `latency_pong` | — | RTT measurement used to auto-throttle broadcasts |
| `/` SocketIO `auto_adjust_rate` | — | Client-driven broadcast interval (clamped 0.2 – 1.5 s) |

REST routes from `interfaces/api.py` (`/api/health`, `/api/observer`, `/api/dii`, `/api/phi`, `/api/hive`, `/api/chat/stream`, `/api/tools`) are listed in the root README; they ship on the uvicorn surface, not the Flask one.

### Compatibility shims

- `/api/tags` lets tools that expect an Ollama server (Reins, Open WebUI) discover the bot.
- `/api/chat` accepts the Ollama `{model, messages}` body and responds in the matching shape.
- `/v1/chat/completions` accepts the OpenAI body and responds with a `chat.completion` envelope (token counts are stubbed at `0`).

These are best-effort façades for client compatibility — they do **not** implement streaming or function calling for the external schema.

---

## Docker

The repo ships a slim CPU-only image.

```dockerfile
FROM python:3.12-slim
# system libs for native deps (sndfile, portaudio, sqlite, build chain)
RUN apt-get install -y gcc g++ libffi-dev libssl-dev libsndfile1 portaudio19-dev sqlite3 curl
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
RUN pip install -e .                  # installs the `infj_bot` namespace package
RUN mkdir -p /app/chroma_db /app/data
EXPOSE 7860
CMD ["python", "interfaces/web_app.py"]
```

Notes:

- The project itself is installed `-e .` so that `from infj_bot.core...` resolves the same way it does in development. Without this the container starts but every import fails (see `d722d43`).
- `evals/` was removed from `.dockerignore` in `6f86262` so the image now has the ablation runner available at runtime.
- Data persists at `/app/chroma_db` and `/app/data`. Override with `INFJ_DATA_DIR=/some/mount` and bind-mount accordingly to keep memory across deployments.

### Build & run locally

```bash
docker build -t drift .
docker run --rm -p 7860:7860 \
  -e API_KEY=$GEMINI_API_KEY \
  -v $(pwd)/drift-data:/app/data \
  -v $(pwd)/drift-chroma:/app/chroma_db \
  drift
# open http://localhost:7860
```

---

## Hugging Face Spaces

The repo is configured as an HF Space (SDK `docker`, port `7860`). The frontmatter at the top of [`README.md`](../README.md) is the Space manifest:

```yaml
---
title: PHI // DRIFT
emoji: 🧠
colorFrom: red
colorTo: blue
sdk: docker
app_port: 7860
pinned: true
license: apache-2.0
short_description: Homeostatic cognitive architecture for AI companions
---
```

Constraints to keep in mind for Spaces:

- `app_port` and `EXPOSE` must agree. We pin both to `7860`.
- `short_description` must be present and under the HF length limit (`a08a27b` fixed that).
- The Space runs without persistent disk by default — set `INFJ_DATA_DIR` to a writable path and accept that the store resets between builds, or attach a Space-paid persistent volume.
- HF Spaces does not run Ollama. Either rely on cloud providers (`API_KEY`, `GROQ_API_KEY`, `KIMI_API_KEY`) or set `INFJ_USE_LOCAL_FALLBACK=false`.

### Secrets

Add the following in Space Settings → **Repository secrets** (they map to env vars):

| Secret | Required when |
|--------|---------------|
| `API_KEY` (Gemini) | Always (or one of `GEMINI_API_KEY`, `GOOGLE_API_KEY`) |
| `GROQ_API_KEY`     | Using Groq inference |
| `KIMI_API_KEY`     | Using Kimi inference |
| `BUGCROWD_API_KEY` | Using `/bug submit` |
| `INFJ_DATA_DIR`    | If attaching persistent storage |

See [`.env.example`](../.env.example) for the full list and defaults.

---

## Environment variables (deployment subset)

The full table lives in `core/config.py`. The ones that matter most for a deployed instance:

| Variable | Default | Effect |
|----------|---------|--------|
| `PORT`                 | `7860` | Web server port |
| `INFJ_DATA_DIR`        | repo root | Where Chroma + every SQLite file goes |
| `INFJ_PRIMARY_MODEL`   | `gemini-2.5-flash` | Cloud primary |
| `INFJ_CRITIC_MODEL`    | `gemini-2.5-flash` | Optional internal critic |
| `INFJ_USE_LOCAL_FALLBACK` | `true` | Disable in cloud deployments without Ollama |
| `INFJ_LOCAL_MODEL`     | `qwen3:4b` | Local model name |
| `OLLAMA_HOST`          | `http://localhost:11434` | Local LLM endpoint |
| `INFJ_MAX_TOTAL_PROMPT_CHARS` | `12000` | Token budget governor |
| `REFLECTION_INTERVAL`  | `10` | Turns between automatic reflection cycles |
| `INFJ_AUTHORIZED_TARGETS` | `example.com,localhost` | Domains the bughunter mode may touch |
| `DRIFT_LOCAL_TIMEOUT`  | set per call | Picked up by the local runner; see [SHADOW_GOVERNANCE.md](SHADOW_GOVERNANCE.md) §3 |

---

## Health & smoke checks

```bash
# Local CLI + REST sanity
./scripts/health_check.sh
LIVE_API_CHECK=1 ./scripts/health_check.sh   # hits a provider once when keys exist

# In the running web container
curl http://localhost:7860/api/growth
curl -X POST http://localhost:7860/api/command \
  -H 'content-type: application/json' \
  -d '{"command":"health","args":""}'
```

The `/observatory` route also functions as a visual smoke test — if SocketIO is wired up correctly you'll see deltas streaming within a second of loading the page.

---

## Common pitfalls

- **`ModuleNotFoundError: infj_bot`** — Dockerfile missed the `pip install -e .` step. Rebuild after pulling.
- **YAML frontmatter errors on HF** — `pinned`, `license`, and `short_description` are validated. Check `README.md` against `a08a27b`/`d1805e8`.
- **Browser can't connect to WebSocket** — the broadcast loop and SocketIO require gevent monkey-patching at the very top of `web_app.py`. Do not import anything before `monkey.patch_all()`.
- **`/glyph` returns 500 with "No such file"** — the route falls back to a developer-machine path. Make sure `interfaces/templates/phi_glyph_system.html` is committed (it is, since `05102c1`).
- **Trial sessions expire mid-conversation** — `/trial` issues a 30-minute UUID; subsequent `/api/chat` calls with that `session_id` after 1800 s get HTTP 403. Use `/` for unmetered access.

---

## Related docs

- [README.md](../README.md) — getting started, architecture, commands
- [HOW_INFJ_BOT_WORKS.md](HOW_INFJ_BOT_WORKS.md) — request lifecycle
- [SECURITY.md](../SECURITY.md) — secret hygiene & reporting
- [.env.example](../.env.example) — full env var reference
