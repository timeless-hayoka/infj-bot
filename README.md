# INFJ Bot

Local **AI companion** with durable memory, multiple chat modes, reflection helpers, and optional tools. Built for thoughtful, continuity-first conversation—not a one-shot chat window.

**Repository:** [github.com/timeless-hayoka/infj-bot](https://github.com/timeless-hayoka/infj-bot)

## Features

- **Long-term memory** — Chroma-backed retrieval with metadata (mode, emotion hints, importance, etc.). Guardrails treat memories as context, not absolute truth.
- **Chat modes** — `companion`, `engineer`, `critic`, `coach`, `clarity`, `researcher`, `bughunter`, `drift`, `quiet` (see slash commands). `drift` is the safe companion/guardian/co-architect posture backed by curated Drift-derived concepts.
- **Layered “cognitive” context** — Prompt assembly combines goals, documents, relationship/values-style signals, and safety rails before calling the model.
- **Dual-model path** — Primary Gemini generation plus an internal critic pass when configured; optional **Ollama** fallback if the cloud API is unavailable (see config).
- **Interfaces** — Interactive terminal chat, **Rich** TUI, one-shot `ask`, and a **FastAPI** web UI on `127.0.0.1:8765`.
- **Commands** — Focus, planning, memory CRUD, reflection, cognitive-dissonance helper, todos, document ingest/RAG, tool listing and audit, and more (see below).
- **Offline checks** — `health` script compiles critical modules, runs a small stress harness, and verifies Chroma (optional live Gemini ping).

## Requirements

- **Python 3.12+** (project uses a local `venv`; matching that version avoids surprises).
- **Google Gemini API** key ([Google AI Studio](https://aistudio.google.com/)) via environment variables (see Configuration).
- **Optional:** [Ollama](https://ollama.com/) on `localhost` (or set `OLLAMA_HOST`) for local fallback models.
- Disk space for **Chroma** persistence under `chroma_db/`, SQLite state files, and optional Piper **voice** assets (`.onnx` files are gitignored—install separately if you use voice).

## Quick start

```bash
git clone https://github.com/timeless-hayoka/infj-bot.git
cd infj-bot
python3 -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env: set API_KEY (or GEMINI_API_KEY / GOOGLE_API_KEY)

python seed_cognition.py   # Recommended on first run: seeds Chroma concepts (health check expects non-empty memory)
./scripts/health_check.sh  # Offline checks; add LIVE_API_CHECK=1 for one live model call
```

Run the CLI (default is interactive chat if you invoke the launcher with no subcommand):

```bash
python cli.py chat
# or, if installed: infj_bot chat
python cli.py ask what should I focus on today?
python cli.py tui
python cli.py web    # then open http://127.0.0.1:8765
python cli.py health [--live]
python cli.py backup [optional-output.tar.gz]
python cli.py restore /media/crexs/PortableSSD/infj_bot_backup [target-dir]
python cli.py path   # print project root
```

Project scripts under `scripts/` (`run_bot.sh`, `run_web.sh`, `backup.sh`, etc.) assume `venv` is activated from the project root—same as the CLI helpers above.

## Configuration

| Variable | Purpose |
|----------|---------|
| `API_KEY` | Primary Gemini key (aliases: `GEMINI_API_KEY`, `GOOGLE_API_KEY`) |
| `API_KEY_FILE` | Path to a UTF-8 file: first non-comment line is used as Gemini key if env vars are unset (`GEMINI_API_KEY_FILE` / `GOOGLE_API_KEY_FILE` same) |
| `INFJ_PRIMARY_MODEL` | Default: `gemini-2.5-flash` |
| `INFJ_CRITIC_MODEL` | Critic model name |
| `REFLECTION_INTERVAL` | Tunable reflection cadence (default `10`) |
| `INFJ_AUTHORIZED_TARGETS` | Comma-separated hosts/domains pre-authorized for bug-hunter style tooling |
| `INFJ_USE_LOCAL_FALLBACK` | `true`/`false` — try Ollama when cloud fails |
| `INFJ_LOCAL_MODEL` | Ollama model tag (default `qwen3:4b`) |
| `OLLAMA_HOST` | Default `http://localhost:11434` |

See `.env.example` for a minimal template.

## Chat slash commands (CLI / web)

Common commands (full list in `docs/DELL_HANDOFF.md`):

| Command | Purpose |
|---------|---------|
| `/help`, `/status`, `/modes` | Help and state |
| `/mode <name>` | Set mode (companion, engineer, critic, coach, clarity, researcher, bughunter, drift, quiet) |
| `/focus`, `/plan` | Goal framing |
| `/history`, `/memory …` | Session and long-term memory |
| `/reflect`, `/dissonance` | Reflection helpers |
| `/reset` | Clear session brain context (not long-term memory) |
| `/todo …` | Simple todos |
| `/ingest`, `/docs` | Document store / search |
| `/tools`, `/tools audit` | Tool surface and audit log |

## Architecture (high level)

- **`brain.py`** — Gemini (and optional local) generation, critic, tool orchestration.
- **`prompt_builder.py`** — Assembles user message + retrieved memory + mode rails + cognitive snippets.
- **`memory.py`** — Chroma persistence and retrieval; secrets scrubbing on save.
- **`main.py`** — Async chat loop, proactive/background behavior, integration with goals, documents, and subsystems (`being`, emotions, etc.).
- **`api.py`** — FastAPI app for the web UI (served via `uvicorn` in `scripts/run_web.sh`).

Concept seeding versus the separate **Drift** project is documented in `docs/DRIFT_AI_INTEGRATION.md` (Drift’s codebase is **private**; this repo only ships derived cognition seeds, not a submodule). Drift mode pulls those curated concepts into the prompt when relevant.

## Testing

```bash
source venv/bin/activate
pytest
```

Some tests may expect optional dependencies or local models; start with `pytest tests/test_bot.py` if you want a narrow run.

## Security

See `SECURITY.md`. **Never commit `.env`**, API keys, or raw database exports. If a key was ever pushed, rotate it in the provider console.

## Docs in this repo

| File | Contents |
|------|----------|
| [HOW_INFJ_BOT_WORKS.md](docs/HOW_INFJ_BOT_WORKS.md) | **Full breakdown** of architecture and behavior — best file to forward to collaborators |
| [DELL_HANDOFF.md](docs/DELL_HANDOFF.md) | Longer handoff: commands, backup, voice notes |
| [DRIFT_AI_INTEGRATION.md](docs/DRIFT_AI_INTEGRATION.md) | How Drift-derived concepts were seeded (Drift repo is private) |
| [UPGRADE_BACKLOG.md](docs/UPGRADE_BACKLOG.md) | Maintainer-facing improvement ideas |
| [SECURITY.md](SECURITY.md) | Reporting and secret-handling expectations |

---

INFJ Bot is a personal/serious hobby project evolving toward a product-ready companion. Issues and PRs are welcome for clear bugs or docs; for large features, open a discussion first.
