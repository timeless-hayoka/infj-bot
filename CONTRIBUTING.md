# Contributing to PHI // DRIFT (INFJ Bot)

Thank you for your interest in PHI // DRIFT. This is a personal companion AI with a layered cognitive architecture, so contributions should align with the project's philosophical and technical goals.

## Development Setup

```bash
# Clone
git clone https://github.com/timeless-hayoka/infj-bot.git
cd infj-bot

# Create virtual environment
python3.12 -m venv .venv
source .venv/bin/activate

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
infj-bot/
├── __main__.py                 # `python -m infj_bot` entry
├── config_adapter.py           # Resolves DATA_DIR / PROJECT_ROOT / DB paths
├── verify_architecture.py      # Standalone architecture check
├── core/                       # Cognitive runtime
│   ├── brain.py                # DriftBrain — Gemini / Groq / Kimi / Ollama
│   ├── memory.py               # DriftMemory — Chroma + secret scrubbing
│   ├── cognitive_orchestrator.py
│   ├── prompt_builder.py
│   ├── prompt_budget.py
│   ├── security_defense.py     # Pre-LLM scanner (4 attack categories)
│   ├── logic_chain.py          # Reasoning-trace memory
│   ├── dmu_scoring.py          # Memory Prioritization Score (additive MPS)
│   ├── experiment_control.py   # Freeze flags and run lifecycle
│   ├── continuity_vector.py    # 5-axis behavioral continuity
│   ├── phi_proxy.py            # IIT-inspired functional analog
│   ├── phi_council.py          # Aura/Logic/Meme/Vibe/Ethos/Pulse/Nexus mapping
│   ├── commands.py             # Slash-command router
│   ├── plugins/                # Cognitive plugins (being, shadow, …)
│   └── hive/                   # Elysium / Nexus / Council deliberation
├── interfaces/                 # User-facing entrypoints
│   ├── cli.py                  # `infj-bot` typer dispatcher
│   ├── main.py                 # Async CLI chat loop
│   ├── api.py                  # FastAPI REST + SSE (port 8765)
│   └── web_app.py              # Browser UI (port 5000)
├── evals/                      # Evaluators and baseline reports
├── tests/                      # pytest + ablation_suite.py + stress tests
├── tools/                      # Self-check tools
├── mcp/                        # Optional MCP servers (Gmail, …)
├── scripts/                    # Shell helpers (run_*, backup, health_check)
├── docs/                       # Documentation
│   ├── README.md               # Doc index
│   ├── HOW_INFJ_BOT_WORKS.md   # End-to-end flow
│   ├── SUBSYSTEMS.md           # Security / logic chain / DMU / etc.
│   ├── GLOSSARY.md
│   └── FALSIFIABILITY.md       # DRIFT's testable claim
└── automation/                 # Outreach + scheduling automation
```

## Code Standards

- **Python 3.12+** required.
- **Line length:** 100 characters (enforced by `ruff`).
- **Imports:** `isort` style — stdlib first, third-party second, `infj_bot.*` last.
- **Type hints:** encouraged on new functions; not required for legacy modules.
- **Logging:** use `logging.getLogger("infj_bot.<module>")`; never `print()` in library code.
- **Exceptions:** catch specific exceptions; avoid bare `except:`.
- **Security:** scrub secrets before persistence; validate all paths against `SAFE_HOME`.

## Git Workflow

1. **Branch:** `git checkout -b feature/short-description`.
2. **Commit:** clear, imperative messages (`Add rate limiter`, `Fix path traversal`).
3. **Test:** run `pytest` before pushing (see below).
4. **Lint:** `ruff check .` and `ruff format .`.
5. **Push:** `git push -u origin feature/short-description`.
6. **PR:** open against `master` with a clear description.

## Running Tests

```bash
# Full pytest suite
pytest

# Security defense (22 tests)
python core/security_defense_test.py

# Logic chain / reasoning trace (25 tests)
python core/logic_chain_test.py

# Stress (28 tests)
python tests/test_stress.py

# Ablation suite (live LLM calls — slow on CPU)
python tests/ablation_suite.py --conditions A,B,C,D,E,F --diverse 2 --live

# Architecture import smoke test
python verify_architecture.py
```

## Documentation

When you change behavior that contributors or operators need to know, update:

- [`README.md`](README.md) — only for top-level capabilities or new install steps.
- [`docs/HOW_INFJ_BOT_WORKS.md`](docs/HOW_INFJ_BOT_WORKS.md) — the end-to-end flow if you change the chat-turn pipeline.
- [`docs/SUBSYSTEMS.md`](docs/SUBSYSTEMS.md) — the canonical reference for the security scanner, logic chain, DMU, experiment control, continuity vector, council, and phi proxy.
- [`docs/GLOSSARY.md`](docs/GLOSSARY.md) — for new project-local terminology.

Verify against source code, do not paraphrase from memory. Keep docs concise and scannable.

## Areas That Need Help

- **Test coverage:** several cognitive plugins still have no targeted tests.
- **Type hints:** legacy modules lack annotations.
- **Performance:** ChromaDB query latency on large collections.
- **Security:** continuous audit of tool execution paths for injection vectors.
- **DMU tuning:** `MPS_WEIGHTS` in `core/dmu_scoring.py` are unvalidated; structured sensitivity analysis is welcome.

## Communication

- Open an issue before major architectural changes.
- Keep PRs focused — one concern per PR.
- Respect the project's philosophical tone (depth + falsifiability, not corporate AI).
