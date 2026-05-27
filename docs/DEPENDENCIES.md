# Dependency Map

This document groups the INFJ Bot's dependencies by purpose and identifies candidates for slimming.

## Core Runtime (Required)

| Package | Purpose | Slimmable? |
|---------|---------|------------|
| `chromadb` | Vector database for semantic memory | No |
| `sentence-transformers` | Local embeddings (MiniLM) | No |
| `transformers` | Backbone for sentence-transformers / HF tokenizers | No |
| `huggingface_hub` | Model download for embeddings (pinned `<1.0`) | No |
| `torch` | Required by sentence-transformers | No |
| `numpy` | Numerical ops | No |
| `python-dotenv` | `.env` file loading | No |
| `PyYAML` | Config / prompt YAML parsing | No |
| `pydantic` | Data validation (FastAPI, MCP) | No |
| `psutil` | Host CPU/RAM sampling for `host_load.py` | Optional — set `INFJ_DISABLE_HOST_LOAD=1` to drop |

## LLM Providers (Pick One+)

| Package | Provider | Slimmable? |
|---------|----------|------------|
| `google-genai` | Gemini (new SDK) | Keep both or pick one |
| `google-generativeai` | Gemini (legacy SDK) | Keep both or pick one |
| `google-auth-*` | Google auth flows | If using Gemini |
| `ollama` | Local LLM fallback | If using local models |

**Slim option:** If you only use Gemini, drop `ollama` and Anthropic packages. If you only use local models, drop all Google packages.

## Web & API

The deployable image (Docker / Hugging Face Spaces) boots **Flask + Flask-SocketIO on gevent**. The FastAPI path is the headless REST alternative — both stacks ship in `requirements.txt` so any interface can be selected at startup.

| Package | Purpose | Slimmable? |
|---------|---------|------------|
| `Flask`            | Web server for `interfaces/web_app.py` | No (unless CLI-only) |
| `Flask-SocketIO`   | Real-time observatory deltas | No (unless CLI-only) |
| `gevent`           | Async worker for SocketIO | No (unless CLI-only) |
| `gevent-websocket` | WebSocket transport for gevent | Transitive |
| `python-socketio`  | SocketIO protocol | Transitive |
| `python-engineio`  | Engine.IO transport | Transitive |
| `simple-websocket` | Fallback WebSocket impl | Transitive |
| `fastapi`          | Headless REST API (`interfaces/api.py`) | Drop with uvicorn for Flask-only |
| `uvicorn`          | ASGI server for FastAPI | Drop with fastapi |
| `sse-starlette`    | SSE streaming for `/api/chat/stream` | Drop with FastAPI |
| `starlette`        | FastAPI dependency | Transitive |
| `httpx`            | HTTP client | No |
| `websockets`       | WebSocket support | Transitive |

**Slim option:** Run in CLI-only mode (`python interfaces/main.py`) and drop Flask + FastAPI + their transports.

## Voice & Audio

| Package | Purpose | Slimmable? |
|---------|---------|------------|
| `faster-whisper` | Speech-to-text | Yes — drop if no voice |
| `piper-tts` | Text-to-speech | Yes — drop if no voice |
| `sounddevice` | Audio I/O | Yes — drop if no voice |
| `soundfile` | Audio file handling | Yes — drop if no voice |

**Slim option:** Remove all four if you never use voice commands.

## Tools & Integrations

| Package | Purpose | Slimmable? |
|---------|---------|------------|
| `playwright` | Browser automation | Yes — drop if no web tools |
| `duckduckgo-search` | Web search | Yes — drop if no search |
| `PyPDF2` | PDF parsing | Yes — drop if no PDF tools |
| `mcp` | Model Context Protocol | Yes — drop if no MCP servers |
| `markdown` | Markdown rendering | Transitive |

## Data Science (Optional)

| Package | Purpose | Slimmable? |
|---------|---------|------------|
| `pandas` | Data analysis | Yes — only used in some tools |
| `matplotlib` | Plotting | Yes — only used in some tools |

## Dev / Quality (Not in requirements.txt)

| Package | Purpose | Install |
|---------|---------|---------|
| `pytest` | Testing | `pip install pytest` |
| `ruff` | Linting + formatting | `pip install ruff` |
| `mypy` | Type checking | `pip install mypy` |
| `bandit` | Security scanning | `pip install bandit` |
| `detect-secrets` | Secret detection | `pip install detect-secrets` |

## Slimming Guide

To create a minimal install for headless, text-only operation:

```bash
# Core only
pip install chromadb sentence-transformers torch numpy python-dotenv PyYAML pydantic httpx psutil

# Pick your LLM backend
pip install google-genai google-generativeai google-auth-oauthlib
# OR
pip install ollama

# Optional: web UI (Flask stack — what the Docker image / HF Space uses)
pip install Flask Flask-SocketIO gevent gevent-websocket python-socketio python-engineio simple-websocket

# OR: headless REST only (FastAPI stack)
pip install fastapi uvicorn sse-starlette
```

This drops ~500MB+ of voice, browser, and data science dependencies.

## Where new subsystems pull from

These modules added in recent commits do **not** introduce new third-party dependencies — they reuse what's already pinned:

| Module | Uses |
|--------|------|
| `core/bug_bot.py` + plugins | stdlib only (`urllib`, `sqlite3`, `subprocess`); external binaries `subfinder` / `nuclei` / `ffuf` if installed |
| `core/shadow_governance.py` | stdlib `math`, `dataclasses` |
| `core/task_mutator.py`      | stdlib `dataclasses`, `enum`, `uuid`, `time` |
| `core/retry_wrapper.py`     | stdlib `os`, `time`, `functools` |
| `core/continuity_vector.py` | `numpy` |
| `hive_mind/`                | stdlib only (`uuid`, `dataclasses`, `enum`) |
