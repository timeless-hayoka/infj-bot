# INFJ Bot Dell Handoff

This folder contains the INFJ companion bot, its seeded Chroma memory, and the `.env` file used by `brain.py`.

## Run On The Dell

```bash
cd infj_bot
./scripts/setup_dell.sh
./scripts/run_bot.sh
```

## CLI

```bash
infj_bot
infj_bot chat
infj_bot ask "What should I focus on today?"
infj_bot ask --no-tools "Just chat, no tools"
infj_bot web
infj_bot health
infj_bot health --live
infj_bot backup
infj_bot path
```

The launcher lives at `~/.local/bin/infj_bot` and uses this project's existing `venv`.

## Web UI

```bash
./scripts/run_web.sh
```

Then open `http://127.0.0.1:8765`.

The web UI is a FastAPI app with:
- Markdown rendering
- SSE streaming responses (toggle with the SSE button)
- Growth avatar panel
- Mobile-responsive layout

## Health Check

```bash
./scripts/health_check.sh
LIVE_API_CHECK=1 ./scripts/health_check.sh
```

The default health check is offline and does not spend API quota. `LIVE_API_CHECK=1` calls Gemini once.

## Chat Commands

- `/help`
- `/status`
- `/modes`
- `/mode companion|engineer|critic|coach|clarity|researcher|bughunter|drift|quiet`
- `/focus <goal or mess>`
- `/plan <goal>`
- `/history [count]`
- `/memory <query>`
- `/memory learn <name>: <description>`
- `/memory forget <name>`
- `/memory edit <name>: <new description>`
- `/memory count`
- `/memory export [path]`
- `/memory import <path>`
- `/memory compact [days]` — prune old low-importance interactions (default 30 days)
- `/reflect [topic]`
- `/dissonance <situation>`
- `/reset` — clear session history and brain context (does not erase long-term memory)
- `/todo add <title>`
- `/todo list`
- `/todo done <id>`
- `/todo delete <id>`
- `/todo priority <id> low|normal|high`
- `/ingest <file or directory> [tags]` — load documents into RAG
- `/docs <query>` — search ingested documents
- `/tools` — list available agent tools
- `/tools audit [count]` — show recent tool calls
- `/growth`

## Agent Tools

The bot can use tools during conversation:

- `read_file` — read files within the home directory
- `write_file` — write files within the home directory
- `shell` — run shell commands (sandboxed, timeout, blocklist)
- `execute_terminal_command` — compatibility wrapper for guarded shell commands
- `write_to_cold_storage` — save notes/artifacts under `BLKKNIGHT_RECOVERY/`
- `run_nuclei_scan` — high/critical Nuclei scan for explicitly authorized targets only
- `web_search` — DuckDuckGo search
- `run_python` — execute Python in a sandboxed subprocess
- `get_datetime` — current time
- `list_directory` — list directory contents

Tool use is enabled by default. Use `--no-tools` with `ask` to disable.
Agent tool calls are logged to `tool_audit.jsonl` with redacted content/code previews.

## Phase 2 Features

### Local Emotion Classifier
Replaces keyword matching with `j-hartmann/emotion-english-distilroberta-base` (DistilRoBERTa, ~66MB). Runs offline on CPU. Falls back to lexicon if the model is unavailable.

### Smart Proactive Triggers
Proactive thoughts fire based on:
- Time away + detected stress in last interaction
- Upcoming reminders within 4 hours
- Unresolved cognitive dissonance (score > 0.5)
- Occasional philosophical prompts

### Document RAG
Ingest text files, markdown, code, and PDFs into a separate Chroma collection. The bot retrieves relevant document chunks during chat.

## Phase 3 Features

### FastAPI Web UI with SSE Streaming
- Replaced the basic HTTP server with FastAPI + Uvicorn
- Responses stream token-by-token via Server-Sent Events
- Markdown rendering with `marked.js`
- Dark theme with GitHub markdown CSS

### MCP Server
Expose the bot as a Model Context Protocol server:

```bash
./venv/bin/python mcp_server.py
```

Available MCP tools:
- `emotional_clarity` — analyze emotional tone
- `dissonance_map` — map cognitive dissonance
- `memory_search` — search long-term memory
- `document_search` — search ingested documents
- `todo_list` / `todo_add` / `todo_complete` — goal management
- `companion_think` — ask the INFJ companion to reflect
- `ingest_document` — load files into RAG

Connect from Claude, Cursor, or any MCP client via stdio.

### Voice Layer (STT + TTS)
- **STT**: `faster-whisper` (base model, CPU, int8) — transcribe audio files
- **TTS**: `piper-tts` with `en_US-lessac-medium` voice — synthesize speech
- **Wake word**: Simple keyword matching on transcription
- Voice model files live in `voices/`

### Behavioral Testing Suite
`tests/test_persona.py` contains regression tests for:
- Cyber safety boundaries (refuses offensive ops, allows defensive)
- Mode rails (bughunter, researcher, etc.)
- Shell blocklist and path sandboxing
- Emotion classifier accuracy
- Dissonance detector accuracy
- Output format consistency

## Tests

```bash
./venv/bin/python -m unittest discover -s tests -v
```

## Notes

- `brain.py` loads `API_KEY` from `.env`; do not paste the key directly into source code.
- Optional `.env` model overrides: `INFJ_PRIMARY_MODEL` and `INFJ_CRITIC_MODEL`.
- `brain.py` also accepts `GEMINI_API_KEY` or `GOOGLE_API_KEY` if `API_KEY` is not set.
- `chroma_db/` contains the seeded cognition and Drift Soul memory concepts.
- `history.jsonl` stores local session history after chats begin.
- `goals.db` stores the todo/goal tracker (SQLite).
- `voices/` stores the Piper TTS voice model.
- `seed_cognition.py` can re-seed or update the memory concepts.
- `stress_test.py` can verify local memory/retrieval without using API quota.
- Preserve `chroma_db/` as a directory when copying backups.
- Do not commit `.env`, `venv/`, `__pycache__/`, or generated archives.
