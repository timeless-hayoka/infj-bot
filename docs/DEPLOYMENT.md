# Deployment

How to package and run **PHI // DRIFT** in containers, on Hugging Face
Spaces, and on a workstation. Pulled directly from `Dockerfile`,
`interfaces/web_app.py`, `interfaces/api.py`, `core/brain.py`, and the
recent deploy-prefixed commit history.

> Use this together with [HOW_INFJ_BOT_WORKS.md](HOW_INFJ_BOT_WORKS.md)
> for architecture context and [DEPENDENCIES.md](DEPENDENCIES.md) for
> what each major package does.

---

## 1. Interfaces & default ports

The repo ships **three** runnable surfaces. They are independent — each
constructs its own `DriftBrain`, `DriftMemory`, `ChatHistory`, and
`BotState`.

| Interface | Entry point | Server | Default port | Suitable for |
|-----------|-------------|--------|--------------|--------------|
| CLI chat | `python interfaces/main.py` | stdin/stdout + Rich | n/a | Local dev, scripted use |
| REST API + SSE | `python interfaces/api.py` (or `uvicorn interfaces.api:app`) | FastAPI on uvicorn | `127.0.0.1:8765` | Programmatic access, streaming |
| Dashboard / Web UI | `python interfaces/web_app.py` | Flask + Flask-SocketIO over **gevent** | `0.0.0.0:7860` | Browser UI, Hugging Face Spaces |

The Web UI is the canonical container entrypoint. It exposes:

- `/` — PHI Glyph System dashboard (HTML).
- `/observatory` — Observatory live state, when the optional
  `hive_mind/` symlink resolves.
- `/api/chat` — JSON chat endpoint used by the dashboard.
- `/v1/chat/completions` — minimal OpenAI-compatible adapter
  (single-turn).
- `/api/command` — slash-command surface (`/memory`, `/chain`,
  `/security`, `/mode`, etc.).
- Socket.IO channel — delta-state broadcasts (see
  [DRIFT_UPGRADE_MAY_2024.md](DRIFT_UPGRADE_MAY_2024.md)).

The `PORT` environment variable overrides `7860` if Spaces or another
host injects its own value.

---

## 2. Docker

The shipped `Dockerfile` is a single-stage `python:3.12-slim` build.

```dockerfile
FROM python:3.12-slim
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ libffi-dev libssl-dev \
    libsndfile1 portaudio19-dev \
    sqlite3 curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY . .

# Required: the project imports itself as `infj_bot.*`
RUN pip install --no-cache-dir -e .

RUN mkdir -p /app/chroma_db /app/data
EXPOSE 7860
CMD ["python", "interfaces/web_app.py"]
```

### Why `pip install -e .` is required

Every interface uses fully-qualified imports such as
`from infj_bot.core.brain import DriftBrain`. The `infj_bot` package is
mapped to the repo root in `pyproject.toml`
(`package-dir = {"infj_bot" = "."}`). Without an install step the
package is not on `sys.path` inside the container and startup fails with
`ModuleNotFoundError: No module named 'infj_bot'`. Installing in
**editable mode** keeps the bind-mounted code authoritative while still
making the namespace importable.

### Build & run locally

```bash
# Build
docker build -t phi-drift .

# Run (Web UI on http://localhost:7860)
docker run --rm -p 7860:7860 \
  -e API_KEY="$GEMINI_API_KEY" \
  -e DRIFT_USE_LOCAL_FALLBACK=false \
  -v phi-drift-data:/app/data \
  -v phi-drift-chroma:/app/chroma_db \
  phi-drift
```

### Persistence

The Dockerfile creates `/app/chroma_db` and `/app/data`. The bot writes
SQLite "state brains", `history.jsonl`, audit logs, and Chroma vectors
under those paths by default. Mount Docker volumes (or pass
`INFJ_DATA_DIR=/app/data`) to survive container restarts.

### `.dockerignore` (what does **not** ship)

```
venv/
__pycache__/
*.pyc
*.pyo
.env
*.db
chroma_db/
data/
history.jsonl
tool_audit.jsonl
voices/*.onnx
voices/*.onnx.json
*.tar.gz
.git/
```

The `evals/` directory **is** included because the package layout in
`pyproject.toml` registers `infj_bot.evals` and excluding it broke the
build before commit `6f86262`.

---

## 3. Hugging Face Spaces

The repository root README ships with the Spaces frontmatter:

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

Spaces uses the **Docker SDK** path — the same `Dockerfile` described
above. `app_port: 7860` lines up with the `EXPOSE 7860` directive and
the default `web_app.py` listener. The `PORT` env var that Spaces
injects is honored by `web_app.main()`:

```python
port = int(os.getenv("PORT", 7860))
socketio.run(app, host="0.0.0.0", port=port, debug=False, use_reloader=False)
```

### Required Space secrets

Set these as **Repository secrets** on the Space (Settings → Variables
and secrets):

| Secret | Purpose |
|--------|---------|
| `API_KEY` (or `GEMINI_API_KEY` / `GOOGLE_API_KEY`) | Primary Gemini access. |
| `GROQ_API_KEY` | Optional, enables the Groq high-speed tier if `DRIFT_USE_GROQ=true`. |
| `KIMI_API_KEY` | Optional, enables Moonshot Kimi if `DRIFT_USE_KIMI=true`. |
| `HF_PRO_TOKEN` | Optional, Hugging Face Pro inference (`DRIFT_USE_HF=true`). |

If **no** cloud keys are present and Ollama is unreachable inside the
Space, `DriftBrain.sdk` falls back to `"none"`. Generation still
returns deterministic placeholder text, so the dashboard renders, but
chat responses will be degraded. CPU Spaces should set
`DRIFT_USE_LOCAL_FALLBACK=false` to skip pointless Ollama probes.

### Common Space pitfalls (already fixed in tree)

These were the recurring failure modes during the recent deploy push;
they are noted here so contributors do not reintroduce them:

1. **Frontmatter constraints** — Spaces validates the YAML block. Keep
   `app_port` numeric, lowercase color values, and a string license
   identifier (commit `a08a27b`).
2. **Module resolution** — drop `RUN pip install -e .` from the
   Dockerfile and every import of `infj_bot.*` will fail at boot
   (commit `d722d43`).
3. **Web server deps** — `Flask`, `Flask-SocketIO`, `gevent`,
   `gevent-websocket`, `python-socketio`, `python-engineio`, and
   `simple-websocket` must be in `requirements.txt`; they are not
   transitively pulled by FastAPI (commit `8d1f0d6`).
4. **`evals/` package** — must be included in the image since
   `pyproject.toml` lists `infj_bot.evals` (commit `6f86262`).

---

## 4. LLM provider routing at runtime

`DriftBrain.__init__` resolves the SDK **once**; per-turn routing then
picks a provider in priority order. The selection is purely env-driven,
so the same image behaves differently in a CPU Space vs. a GPU box vs.
a laptop running Ollama.

```
            ┌────────────────────────────────────────────────────────┐
            │            DriftBrain.__init__ (once)                  │
            │                                                        │
   start ──▶│  DRIFT_PREFER_LOCAL && OllamaBridge.is_available()     │──▶ self.sdk = "local"
            │                                                        │
            │  else if google.genai importable && API_KEY            │──▶ self.sdk = "google.genai"
            │                                                        │
            │  else if google.generativeai importable                │──▶ self.sdk = "google.generativeai"
            │                                                        │
            │  else                                                  │──▶ self.sdk = "none"
            └────────────────────────────────────────────────────────┘
                                       │
                                       ▼
            ┌────────────────────────────────────────────────────────┐
            │              _generate() (per turn)                    │
            │                                                        │
            │  DRIFT_USE_GROQ && GROQ_API_KEY  ──▶ Groq              │
            │  DRIFT_USE_KIMI && KIMI_API_KEY  ──▶ Kimi              │
            │  self.sdk ∈ {google.genai, google.generativeai} ──▶ Gemini │
            │  DRIFT_USE_LOCAL_FALLBACK && Ollama up ──▶ Ollama      │
            │  else ──▶ deterministic offline placeholder            │
            └────────────────────────────────────────────────────────┘
```

The recent fix in commit `bcd8e9a` (relocate SDK initialization from
`get_scope` to `__init__`) was important because earlier the local
fast-path branch had been accidentally placed inside `get_scope`,
making it dead code. `DriftBrain` now consistently sets `self.sdk` at
construction time, which is what every caller (`web_app.py`,
`api.py`, `main.py`, the ablation suite) relies on.

---

## 5. Local workstation

```bash
git clone https://github.com/timeless-hayoka/infj-bot.git
cd infj-bot
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .          # same install step as the Dockerfile
cp .env.example .env       # then edit
```

Run one of:

```bash
python interfaces/main.py                 # CLI loop
python interfaces/api.py                  # FastAPI REST on :8765
python interfaces/web_app.py              # Dashboard on :7860
```

For an offline laptop, start Ollama (`ollama serve`), pull a small
model (`ollama pull qwen3:4b`), and set:

```bash
DRIFT_USE_LOCAL_FALLBACK=true
DRIFT_PREFER_LOCAL=true
DRIFT_LOCAL_MODEL=qwen3:4b
OLLAMA_HOST=http://localhost:11434
```

`DriftBrain.__init__` will short-circuit to the local SDK and never
call Gemini.

---

## 6. Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| `ModuleNotFoundError: infj_bot` at startup | Image was built without `pip install -e .` | Re-add the editable install step in the Dockerfile. |
| Web UI starts but `/` shows "permission denied" or a template path error | The HF Spaces image cannot read absolute host paths the code falls back to | Confirm `interfaces/templates/phi_glyph_system.html` is included in the image (`.dockerignore` does not exclude `interfaces/`). |
| Socket.IO connects but the dashboard never updates | `STRONG_CONTINUOUS_MODE=false` or no provider available, so no telemetry is generated | Set `STRONG_CONTINUOUS_MODE=true` and provide at least one provider key. |
| Bot replies with the deterministic offline placeholder | Every routed provider failed (Groq → Kimi → Gemini → Ollama) | Inspect logs for `Groq error:` / `Kimi error:` / `Gemini ...` lines and verify the matching env toggle + key. |
| Chroma writes fail in container | `/app/data` or `/app/chroma_db` not writable | Mount a volume or pass `INFJ_DATA_DIR` pointing to a writable path. |
| `pip install -e .` fails on Spaces with read-only FS warnings | Build step ran out of disk because `evals/` data was reintroduced | Keep heavy artifacts out of the build context (see `.dockerignore`); only the Python source under `evals/` should be packaged. |

---

## 7. Related docs

- [HOW_INFJ_BOT_WORKS.md](HOW_INFJ_BOT_WORKS.md) — architecture and
  one-turn flow.
- [DRIFT_UPGRADE_MAY_2024.md](DRIFT_UPGRADE_MAY_2024.md) — Gevent /
  Socket.IO / delta-state internals that this deployment relies on.
- [DEPENDENCIES.md](DEPENDENCIES.md) — what can be trimmed for a
  headless or voice-less image.
- [../SECURITY.md](../SECURITY.md) — secret hygiene before shipping
  keys into any deploy target.
