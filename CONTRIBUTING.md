# Contributing to the INFJ Bot

Thank you for your interest in the DRIFT / INFJ Bot project. This is a personal companion AI with a Jungian cognitive architecture, so contributions should align with the project's philosophical and technical goals.

## Development Setup

```bash
# Clone
git clone <repo-url>
cd infj_bot

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Install dev tools (optional but recommended)
pip install ruff mypy bandit detect-secrets pytest

# Copy environment template
cp .env.example .env
# Edit .env with your API keys
```

## Project Structure

```
infj_bot/
  config.py              # Central config, path resolution, API key validation
  brain.py               # Core LLM inference (Gemini + local fallback)
  memory.py              # ChromaDB semantic memory with secret scrubbing
  commands.py            # CLI command router (~40+ commands)
  web_app.py             # FastAPI web UI + Observatory SSE
  emailer.py             # SMTP + Gmail MCP email backend
  rate_limit.py          # Token bucket rate limiters
  maintenance.py         # Automated pruning and upkeep tasks
  hive_mind/             # Distributed-cognition kernel (see docs/HIVE_MIND.md)
    orchestrator.py      # HiveOrchestrator — node registry + heartbeat
    consensus_engine.py  # ConsensusEngine — thread state machine (propose → vote → resolve)
    protocol/dcp.py      # DCPMessage, NodeRole, Resolution
  core/hive/             # Elysium / Nexus / Council (built on the kernel above)
  ... (cognitive modules)
```

## Code Standards

- **Python 3.12+** required
- **Line length:** 100 characters (enforced by ruff)
- **Imports:** `isort` style — stdlib first, third-party second, local third
- **Type hints:** encouraged for new functions; not required for legacy modules
- **Logging:** use `logging.getLogger("infj_bot.<module>")`, never `print()` in library code
- **Exceptions:** catch specific exceptions; avoid bare `except:`
- **Security:** scrub secrets before persistence; validate all paths

## Git Workflow

1. **Branch:** `git checkout -b feature/short-description`
2. **Commit:** clear, imperative messages (`Add rate limiter`, `Fix path traversal`)
3. **Test:** run `python -m pytest tests/` before pushing
4. **Lint:** run `ruff check .` and `ruff format .`
5. **Push:** `git push origin feature/short-description`
6. **PR:** open against `main` with a clear description

## Running Tests

```bash
# Full suite (Hive Mind tests are skipped automatically if the package is unavailable)
python -m pytest tests/ -q

# Hive command + propose + safety-veto tests only
python -m pytest tests/test_bot.py -k hive -q
```

## Areas That Need Help

- **Test coverage:** Most cognitive modules have zero tests
- **Type hints:** Legacy modules lack annotations
- **Documentation:** Cognitive architecture docs for new contributors
- **Performance:** ChromaDB query optimization for large collections
- **Security:** Audit tool execution paths for injection vectors

## Communication

- Open an issue before major architectural changes
- Keep PRs focused — one concern per PR
- Respect the project's philosophical tone (Jungian depth, not corporate AI)
