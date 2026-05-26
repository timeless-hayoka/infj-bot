# Deployment — Docker & Hugging Face Spaces

This guide covers running PHI // DRIFT as a container, in particular the
**Hugging Face Spaces** "Docker SDK" configuration that the repository's
`Dockerfile` and `README.md` frontmatter are set up for.

For local-developer setup (venv, `pip install -r requirements.txt`, running
`interfaces/main.py` directly) see the root [README](../README.md) instead. For
the **CLI** and **FastAPI** surfaces see
[HOW_INFJ_BOT_WORKS.md](HOW_INFJ_BOT_WORKS.md). This document is specifically
about the container entrypoint and the `interfaces/web_app.py` Flask + SocketIO
dashboard that ships with it.

---

## 1. Container layout

The repository root ships with `Dockerfile`, `.dockerignore`, and a
Spaces-compatible YAML frontmatter at the top of `README.md`. Together they
produce a self-contained image that boots straight into the web dashboard.

| File | Purpose |
|------|---------|
| [`Dockerfile`](../Dockerfile) | Python 3.12 slim image, system libs for native deps, `pip install -r requirements.txt`, editable install of the project, `CMD` runs the Flask app. |
| [`.dockerignore`](../.dockerignore) | Strips `venv/`, caches, local databases, voice models, `.env`, and `.git/` from the build context. |
| `README.md` frontmatter | Hugging Face Spaces metadata (`sdk: docker`, `app_port: 7860`, title, emoji, colors, license). Must stay at the very top of the file. |

### 1.1 Why the editable install line matters

```dockerfile
RUN pip install --no-cache-dir -e .
```

`pyproject.toml` declares a flat-layout package: `package-dir = {"infj_bot" = "."}`
re-exposes the repo root as the `infj_bot` namespace. `interfaces/web_app.py`
and `interfaces/api.py` both `from infj_bot.core.*` — without the editable
install those imports fail at container start with `ModuleNotFoundError:
infj_bot`. This was the regression fixed in commit `d722d43`; keep that line.

### 1.2 Default port and entrypoint

```dockerfile
EXPOSE 7860
CMD ["python", "interfaces/web_app.py"]
```

`web_app.py` honors `PORT` (defaulting to `7860`) and binds to `0.0.0.0`, which
is what Hugging Face Spaces routes its public URL to. If you embed the image in
another platform (Cloud Run, Fly, Render, etc.), set `PORT` to whatever the
platform expects and leave `EXPOSE` untouched.

---

## 2. Building and running locally

```bash
# Build
docker build -t phi-drift:latest .

# Run with no API keys — falls back to Ollama if reachable, otherwise canned text
docker run --rm -p 7860:7860 phi-drift:latest

# Run with Gemini + Groq keys
docker run --rm -p 7860:7860 \
  -e API_KEY=$GEMINI_API_KEY \
  -e GROQ_API_KEY=$GROQ_API_KEY \
  -e DRIFT_USE_GROQ=true \
  phi-drift:latest

# Persist memory and Chroma across runs
docker run --rm -p 7860:7860 \
  -e INFJ_DATA_DIR=/data \
  -v $(pwd)/.drift-data:/data \
  phi-drift:latest
```

Then visit `http://localhost:7860/`.

### 2.1 Environment variables that matter at boot

These are the variables `web_app.py` (transitively, via `infj_bot.core.config`)
actually reads. The full list is in [`.env.example`](../.env.example); the
ones below are the minimum useful set for a container deploy.

| Variable | Effect |
|----------|--------|
| `PORT` | Port the Flask + SocketIO server binds (default `7860`). |
| `API_KEY` / `GEMINI_API_KEY` / `GOOGLE_API_KEY` | Gemini access. Without one the brain falls back to local/Ollama. |
| `GROQ_API_KEY` + `DRIFT_USE_GROQ=true` | Enable the Groq high-speed inference tier. |
| `KIMI_API_KEY` + `DRIFT_USE_KIMI=true` | Enable Moonshot Kimi. |
| `INFJ_USE_LOCAL_FALLBACK`, `OLLAMA_HOST`, `INFJ_LOCAL_MODEL` | Local LLM fallback (Ollama). `OLLAMA_HOST` must be reachable from inside the container. |
| `INFJ_DATA_DIR` | Relocates Chroma, SQLite, logs. Mount a volume here for persistence. |
| `INFJ_AUTHORIZED_TARGETS` | Comma-separated allowlist for the bughunter tools. |
| `INFJ_MAX_TOTAL_PROMPT_CHARS`, `INFJ_MEMORY_SEARCH_TOP_K` | Prompt-budget governors. |

`.env` files are not copied into the image (excluded by `.dockerignore`); pass
secrets via `-e` flags, a `--env-file`, or the host platform's secret manager.

---

## 3. Hugging Face Spaces

The repository is structured so that pushing this branch to a Hugging Face
Space with **Docker SDK** is sufficient — no extra `Spaces` config file
required. Spaces reads the YAML block at the top of `README.md`:

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

Constraints Spaces enforces on that block (these have bitten this repo before,
see commits `d1805e8` and `a08a27b`):

- The block must be **the very first thing** in `README.md` — no blank line
  before `---`.
- `emoji` must be a single emoji character.
- `colorFrom` / `colorTo` must be from the [Spaces palette](https://huggingface.co/docs/hub/spaces-config-reference)
  (`red`, `blue`, `green`, `yellow`, `purple`, `pink`, `gray`, `indigo`).
- `short_description` is capped at 200 characters.
- `app_port` must match what the Docker `CMD` actually listens on (here, 7860).

### 3.1 Configuring secrets in Spaces

In the Space's Settings panel add at minimum:

- `API_KEY` (Gemini) — primary path.
- `GROQ_API_KEY` and `DRIFT_USE_GROQ=true` — optional, much faster cold
  responses.

If no keys are configured the bot still boots; it will degrade to canned
fallback text and/or the local Ollama path (which is **not** reachable from a
Hugging Face Space — there is no Ollama daemon inside the runtime). For
production use on Spaces, configure at least one cloud key.

### 3.2 Persistence on Spaces

Spaces filesystems are ephemeral except for `/data` on persistent storage
tiers. If you upgrade the Space to persistent storage, set
`INFJ_DATA_DIR=/data` so Chroma vectors, SQLite state, `history.jsonl`, and the
security audit log survive restarts. Without persistent storage every restart
wipes memory.

---

## 4. The `web_app.py` surface

`interfaces/web_app.py` is the container's only entrypoint. It serves five
related surfaces from a single Flask + SocketIO process.

| Route | Method | Purpose |
|-------|--------|---------|
| `/` | GET | Dashboard HTML (`INDEX_HTML`) — chat panel, growth avatar, mode selector, memory search, links to Observatory and Glyph. |
| `/trial` | GET | Sandbox dashboard. Issues a UUID `session_id` and binds the chat to a 30-minute trial window enforced in `is_trial_active`. |
| `/observatory` | GET | Renders `interfaces/templates/observatory.html`. Subscribes to the SocketIO `observatory_delta` channel for live cognitive-state updates. |
| `/glyph`, `/phi-glyph` | GET | Renders `interfaces/templates/phi_glyph_system.html` — the PHI Glyph visualization dashboard added in commit `05102c1`. |
| `/api/chat` | POST | Primary chat endpoint. Accepts either `{message: str}` (dashboard) or `{messages: [...]}` (Ollama-compatible client). Returns `{reply}` or an Ollama-shaped envelope. |
| `/api/command` | POST | Dispatches a slash command (`mode`, `status`, `reflect`, `memory`, ...) via `infj_bot.core.commands.handle_command`. |
| `/api/growth` | GET | JSON snapshot used by the dashboard's growth avatar (`growth_profile`). |
| `/api/tags` | GET | Ollama `/api/tags` shim so Ollama clients (e.g. Reins) discover the bot as `infj_bot:latest`. |
| `/v1/chat/completions` | POST, OPTIONS | OpenAI Chat Completions shim — same brain, different envelope so any OpenAI-compatible client works. |
| `/api/email` | POST | Stub returning 501. No SMTP backend is wired up by default. |

### 4.1 SocketIO observatory stream

`broadcast_observatory_state()` runs in a daemon thread, polls
`CognitiveOrchestrator.get_delta_state()`, and emits `observatory_delta`
events. Only fields whose values changed since the last broadcast are
included, plus a `timestamp` and a `network_stats` block. The rate is
auto-tuned:

- Client sends `latency_ping` with a wall-clock timestamp every second.
- Server replies `latency_pong`. Client computes round-trip latency.
- Client emits `auto_adjust_rate` with a target interval; the server clamps to
  `[0.2s, 1.5s]` (`broadcast_interval`).

This is the same delta + auto-throttle system described in
[HOW_INFJ_BOT_WORKS § 5](HOW_INFJ_BOT_WORKS.md#5-performance--networking-upgrade-may-2024);
in a container deploy it is what powers the live dashboard at `/observatory`.

### 4.2 Optional `hive_mind` observatory bridge

`web_app.py` attempts to import `drift_bridge.DriftBridge` from
`interfaces/hive_mind/`. That directory is a **symlinked external dependency**
and is not present in this repo's build context. The import is wrapped in a
`try/except` — if missing, `_OBSERVATORY_ENABLED` stays `False` and the rest of
the app boots normally. You only need this module if you are running the full
Hive Mind / Elysium coordination stack.

---

## 5. Troubleshooting

### `ModuleNotFoundError: No module named 'infj_bot'`

The Dockerfile is missing the `pip install -e .` step, or the layer was cached
from before it was added. Rebuild with `--no-cache`.

### Hugging Face Spaces build fails on the README

The YAML frontmatter validator is strict. Common failures:

- Stray whitespace or BOM before the opening `---`.
- Multi-character emoji (joined emoji are not allowed in `emoji:`).
- `short_description` over 200 chars.
- Color outside the Spaces palette.

Fix the block, push again — Spaces rebuilds automatically.

### Dashboard loads but chat replies with fallback text

No cloud LLM key is reachable and the in-container Ollama path is unavailable.
Set `API_KEY` (Gemini) or `GROQ_API_KEY` in the Space's secrets, or point
`OLLAMA_HOST` at a reachable host (this is only useful if you self-host the
container next to an Ollama daemon).

### `/observatory` returns 500

`observatory.html` is loaded from `interfaces/templates/`. If you trimmed the
build context too aggressively (e.g. extending `.dockerignore`), restore that
directory. The route also has a hard-coded `/home/crexs/templates/...`
fallback that only works on the original author's machine.

### Memory loss across restarts

`INFJ_DATA_DIR` is unset, so Chroma and SQLite live inside the ephemeral
container filesystem. On Spaces enable persistent storage and set
`INFJ_DATA_DIR=/data`. Locally mount a host volume as in §2.

---

## 6. Related docs

- [README](../README.md) — quick start, layer map.
- [HOW_INFJ_BOT_WORKS.md](HOW_INFJ_BOT_WORKS.md) — end-to-end request flow,
  prompt assembly, background cycles.
- [DEPENDENCIES.md](DEPENDENCIES.md) — slim-install matrix; the container
  image installs the full superset.
- [SECURITY.md](../SECURITY.md) — secret hygiene and the security defense
  layer.
