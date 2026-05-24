# AGENTS.md

## Cursor Cloud specific instructions

### Project overview

DRIFT (Distributed Response & Integrated Functional Thought) is a Python 3.12+ AI cognitive architecture / chatbot companion. It uses embedded SQLite and ChromaDB for persistence (no external DB servers needed). All state lives under `~/.drift_os/`.

### Environment variables

A `.env` file is required. Copy `.env.example` to `.env`. For CI/testing without live LLMs, set placeholder keys:

```
API_KEY=ci-placeholder-not-for-production
GEMINI_API_KEY=ci-placeholder-not-for-production
GOOGLE_API_KEY=ci-placeholder-not-for-production
```

The `google-genai` SDK requires a non-empty `API_KEY` at import time even when not calling live APIs.

### Package installation

The project must be installed in editable mode (`pip install -e .`) so that tests can import `infj_bot.*` modules. The `pyproject.toml` maps `infj_bot` to the repo root via `package-dir = {"infj_bot" = "."}`.

### Running tests

```bash
source .venv/bin/activate
python -m pytest -q tests/           # 219 tests (~2.5 min)
python core/security_defense_test.py  # 22 standalone tests
python core/logic_chain_test.py       # 25 standalone tests
```

### Lint & format

```bash
ruff check . --exclude venv --exclude .venv --exclude chroma_db --ignore E701,E402
ruff format --check . --exclude venv --exclude .venv --exclude chroma_db
```

The codebase has ~286 pre-existing lint warnings; do not fix them unless your task specifically calls for it.

### Running the application

Three interfaces are available (see README for details):

- **FastAPI REST API**: `python interfaces/api.py` (port 8765)
- **CLI chat loop**: `python interfaces/main.py`
- **Web UI**: `python interfaces/web_app.py` (port 5000, requires extra `flask flask-socketio gevent`)

### System dependencies

`libportaudio2` is required for the `sounddevice` package. Install with `sudo apt-get install -y libportaudio2`.

### Gotchas

- The web UI (`interfaces/web_app.py`) imports `flask`, `flask_socketio`, and `gevent`, which are **not** listed in `requirements.txt`. Install them separately if needed.
- Without a valid LLM API key, the bot falls back to an offline/local response mode. Tests do not require live API access.
- `torch` is a large dependency (~2 GB); initial `pip install` takes a few minutes.
