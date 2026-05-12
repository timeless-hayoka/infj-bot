# Dependency Map

This document groups the INFJ Bot's dependencies by purpose and identifies candidates for slimming.

## Core Runtime (Required)

| Package | Purpose | Slimmable? |
|---------|---------|------------|
| `chromadb` | Vector database for semantic memory | No |
| `sentence-transformers` | Local embeddings (MiniLM) | No |
| `torch` | Required by sentence-transformers | No |
| `numpy` | Numerical ops | No |
| `python-dotenv` | `.env` file loading | No |
| `PyYAML` | Config / prompt YAML parsing | No |
| `pydantic` | Data validation (FastAPI, MCP) | No |

## LLM Providers (Pick One+)

| Package | Provider | Slimmable? |
|---------|----------|------------|
| `google-genai` | Gemini (new SDK) | Keep both or pick one |
| `google-generativeai` | Gemini (legacy SDK) | Keep both or pick one |
| `google-auth-*` | Google auth flows | If using Gemini |
| `ollama` | Local LLM fallback | If using local models |

**Slim option:** If you only use Gemini, drop `ollama` and Anthropic packages. If you only use local models, drop all Google packages.

## Web & API

| Package | Purpose | Slimmable? |
|---------|---------|------------|
| `fastapi` | Web UI + REST API | No (unless headless) |
| `uvicorn` | ASGI server | No (unless headless) |
| `sse-starlette` | SSE streaming for Observatory | No (unless headless) |
| `starlette` | FastAPI dependency | Transitive |
| `httpx` | HTTP client | No |
| `websockets` | WebSocket support | If not using WS chat |

**Slim option:** Run in CLI-only mode (`cli.py`) and drop FastAPI/uvicorn/sse-starlette.

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
pip install chromadb sentence-transformers torch numpy python-dotenv PyYAML pydantic httpx

# Pick your LLM backend
pip install google-genai google-generativeai google-auth-oauthlib
# OR
pip install ollama

# Optional: web UI
pip install fastapi uvicorn sse-starlette
```

This drops ~500MB+ of voice, browser, and data science dependencies.
