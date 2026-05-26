# Deployment Guide

How to package and run PHI // DRIFT outside of a local checkout. Today the
supported deployment targets are **Docker** and **Hugging Face Spaces**
(Docker SDK). Both pathways share the same image definition and the same
entrypoint (`interfaces/web_app.py`).

---

## 1. What gets deployed

The deployed unit is the **web interface** (`interfaces/web_app.py`):

- Flask + Flask-SocketIO with a Gevent worker.
- Serves the chat UI at `/`, the Observatory dashboard at `/observatory`, and
  the PHI Glyph System dashboard at `/glyph`.
- Exposes OpenAI- and Ollama-compatible chat endpoints for external clients.
- Boots a background thread that broadcasts delta-state telemetry over
  WebSockets every 200–1500 ms.

See [`WEB_INTERFACE.md`](WEB_INTERFACE.md) for endpoint-by-endpoint detail.

The CLI (`interfaces/main.py`) and FastAPI surface (`interfaces/api.py`) are
**not** the deployment entrypoints — they exist for local interactive use and
for internal SSE streaming, respectively.

---

## 2. Docker

### 2.1 Image

The repository ships with a single `Dockerfile` at the project root. Key
facts about the image:

| Aspect | Value |
|--------|-------|
| Base image | `python:3.12-slim` |
| Working directory | `/app` |
| System packages | `gcc`, `g++`, `libffi-dev`, `libssl-dev`, `libsndfile1`, `portaudio19-dev`, `sqlite3`, `curl` |
| Python deps | Everything in `requirements.txt`, installed in a single layer |
| Data dirs created | `/app/chroma_db`, `/app/data` |
| Exposed port | `7860` |
| Entrypoint | `python interfaces/web_app.py` |

The audio system packages (`libsndfile1`, `portaudio19-dev`) are required by
`faster-whisper`, `piper-tts`, `sounddevice`, and `soundfile`. Removing them
will break the image build for the current `requirements.txt` even on hosts
that never use voice.

### 2.2 Build and run

```bash
# Build
docker build -t phi-drift:local .

# Run with default config (no API keys = local fallback path only)
docker run --rm -p 7860:7860 phi-drift:local

# Run with API keys and a host-mounted data dir for persistence
docker run --rm -p 7860:7860 \
  -e API_KEY=your_gemini_key \
  -e GROQ_API_KEY=your_groq_key \
  -e INFJ_DATA_DIR=/data \
  -v "$(pwd)/drift-data:/data" \
  phi-drift:local
```

The container listens on `0.0.0.0:7860`. The port is configurable at runtime
via the `PORT` env var (see `interfaces/web_app.py:main`).

### 2.3 Persistent state

By default the container writes ChromaDB and SQLite files under `/app`,
which disappear when the container is removed. To keep memory across
restarts, set `INFJ_DATA_DIR` to a mounted path:

```bash
docker run -p 7860:7860 \
  -e INFJ_DATA_DIR=/data \
  -v phi-drift-data:/data \
  phi-drift:local
```

`INFJ_DATA_DIR` is honored by `config_adapter.py` and is the single switch
for relocating **all** durable state (Chroma, SQLite, transcripts, audits).

---

## 3. Hugging Face Spaces

The repository is configured to deploy directly to a Hugging Face Space
using the **Docker SDK**. The metadata that drives Space creation lives in
the YAML frontmatter at the top of `README.md`:

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

### 3.1 Required guarantees

For the Space to build and route traffic correctly:

1. **`sdk: docker`** — uses the project `Dockerfile`, not Python autobuild.
2. **`app_port: 7860`** — must match `EXPOSE 7860` in the Dockerfile and the
   default port in `interfaces/web_app.py`. If you change one, change all
   three.
3. **`short_description` length** — Hugging Face rejects descriptions longer
   than 60 characters. This constraint was the cause of the
   `deploy: fix YAML frontmatter constraint violations` commit; keep new
   edits inside the limit.
4. **Whitespace-free `colorFrom` / `colorTo`** — must be plain color tokens
   (`red`, `blue`, `indigo`, etc.).

### 3.2 Secrets

Add API keys via the Space's **Settings → Variables and secrets** panel.
Variables to consider:

| Variable | Purpose | Required? |
|----------|---------|-----------|
| `API_KEY` (or `GEMINI_API_KEY`) | Gemini access | One of these is required for cloud inference |
| `GROQ_API_KEY` + `DRIFT_USE_GROQ=true` | Groq high-speed fallback | Optional |
| `KIMI_API_KEY` + `DRIFT_USE_KIMI=true` | Moonshot Kimi fallback | Optional |
| `INFJ_USE_LOCAL_FALLBACK=true` | Allow offline canned responses when all providers fail | Recommended |
| `INFJ_DATA_DIR` | Override durable state path (Spaces filesystem is ephemeral) | Optional |
| `STRONG_CONTINUOUS_MODE` | Enable background drift cycles (`true` by default in code) | Optional |

Spaces do not persist filesystem writes across image rebuilds. If you need
cross-rebuild memory, mount an external store (e.g. an S3-backed dataset)
into `INFJ_DATA_DIR`. Without that, every redeploy starts the bot from a
blank Chroma collection.

### 3.3 Deployment flow

1. Push to the GitHub repository.
2. The Space (configured to track this repo) pulls the new commit.
3. Hugging Face rebuilds the Docker image and restarts the container.
4. The web UI becomes available at `https://<your-space>.hf.space/`.

The Space picks up changes to the `Dockerfile`, `requirements.txt`, and any
file under `interfaces/`, `core/`, or `adapters/`. Pure documentation
changes do not invalidate the cached pip layer because the
`requirements.txt` `COPY` happens before the project `COPY`.

---

## 4. Operational checklist before deploying

1. **Tests** — `pytest` should be green locally; CI also runs against
   `master`.
2. **Requirements** — if you add a Python import, add the package to
   `requirements.txt` with a pinned version. The
   `deploy: add missing web server dependencies` commit was caused by
   forgetting to pin Flask / Flask-SocketIO / gevent.
3. **README frontmatter** — confirm `short_description` is ≤ 60 characters
   and that `app_port` still matches the Dockerfile.
4. **Provider keys** — confirm at least one of `API_KEY`, `GROQ_API_KEY`,
   `KIMI_API_KEY` is set in the Space secrets, or accept that the bot will
   serve only the local-fallback canned response.
5. **Smoke test** — after deploy, hit:
   - `GET /` — chat UI loads
   - `GET /observatory` — dashboard loads
   - `GET /api/tags` — returns a fake Ollama-compatible model list (proves
     the request path is alive)
   - `POST /api/chat {"message": "hello"}` — returns a reply

---

## 5. Common pitfalls

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| Space build fails at `pip install` | Missing native dep for an audio package | Confirm the Dockerfile keeps `libsndfile1` + `portaudio19-dev` |
| `ImportError: cannot import name 'SocketIO'` at runtime | `Flask-SocketIO`/`gevent` not pinned in `requirements.txt` | Re-add the web server pins (see commit `8d1f0d6`) |
| Container starts but Space shows "App failed" | Port mismatch between Dockerfile and frontmatter | Both must be `7860` |
| Observatory page loads but no telemetry updates | WebSocket blocked by reverse proxy or CSP | Use `wss://` from the browser, allow `socket.io` paths |
| Bot replies with the same canned line every time | No provider key set, Ollama unreachable, only offline fallback firing | Configure `API_KEY` / `GROQ_API_KEY`, or point `OLLAMA_HOST` at a reachable instance |
| Memory disappears after redeploy | Default state lives inside the container | Set `INFJ_DATA_DIR` and mount external storage |

---

## 6. See also

- [`WEB_INTERFACE.md`](WEB_INTERFACE.md) — endpoint reference for the
  deployed Flask app.
- [`HOW_INFJ_BOT_WORKS.md`](HOW_INFJ_BOT_WORKS.md) — architecture context
  for what the container actually runs.
- [`DEPENDENCIES.md`](DEPENDENCIES.md) — which packages can be slimmed if
  you build a custom image without voice or browser automation.
- [`../SECURITY.md`](../SECURITY.md) — secret handling and audit logs.
