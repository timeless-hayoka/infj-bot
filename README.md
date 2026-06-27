PHI // DRIFT is the internal companion and reasoning layer. The flagship evidence-gate repo now lives in [ANCHOR](https://github.com/timeless-hayoka/ANCHOR).

---
title: PHI // DRIFT
emoji: 🧠
colorFrom: red
colorTo: blue
sdk: static
pinned: true
license: other
short_description: Homeostatic cognitive architecture for AI companions
---

ANCHOR lives in its own repo now. This repository keeps the internal reasoning layer and companion architecture that support it.

For the companion release-readiness checklist, see [docs/ANCHOR_RELEASE_CHECKLIST.md](docs/ANCHOR_RELEASE_CHECKLIST.md).
For a one-command install plan, run `anchor install laptop` or `anchor install droplet --public-url http://<droplet-ip>:8767/anchor`.
For a short install path, see [docs/ANCHOR_QUICKSTART.md](docs/ANCHOR_QUICKSTART.md).

## Internal Companion Story

This repository keeps the AI companion surface, state management, and guardrails that support the ANCHOR flagship. It turns tool signals into structured cases, requires proof before a finding is promoted, and preserves what was tested, what failed, and what remains unverified.

That framing is intentional:

- It keeps the product anchored to evidence, not vibes.
- It makes failed attempts visible instead of hiding them.
- It preserves the audit trail from signal to remediation.
- It supports honest comparison across tools, runs, and benchmark versions.

For public-facing storytelling, use these reusable assets:

- [90-second demo script](docs/ANCHOR_90_SECOND_DEMO.md)
- [Reusable case study template](docs/ANCHOR_CASE_STUDY_TEMPLATE.md)

Recommended case-study shape:

`Signal -> evidence -> failed attempts -> successful reproduction -> remediation`

That structure works well for benchmark writeups, disclosure posts, conference demos, and researcher outreach because it shows the full path from detection to proof.

# PHI // DRIFT — The Engine for Deep Engagement

<p align="center">
  <img src="docs/assets/drift-banner.jpg" alt="DRIFT wordmark" width="520" />
</p>

[![License](https://img.shields.io/badge/License-Proprietary-red.svg)](file:///home/crexs/drift/LICENSE)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![CI](https://github.com/timeless-hayoka/drift/actions/workflows/ci.yml/badge.svg)](https://github.com/timeless-hayoka/drift/actions/workflows/ci.yml)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.20350249.svg)](https://doi.org/10.5281/zenodo.20350249)

<a href="https://www.buymeacoffee.com/timelesshayoka" target="_blank"><img src="https://cdn.buymeacoffee.com/buttons/v2/default-yellow.png" alt="Buy Me A Coffee" style="height: 60px !important;width: 217px !important;" ></a>

**DRIFT** (Distributed Response & Integrated Functional Thought) solves a critical problem that baseline language models fail to address: user churn due to shallow, amnesic interactions.

We have built a proprietary layer that wraps around enterprise language models to transform stateless APIs into persistent cognitive organisms.

Investors don't fund architectures—they fund leverage. Here is the leverage DRIFT brings to AI applications:

- **Memory → User Retention:** DRIFT continuously synthesizes interactions into a salience-weighted memory graph. The model remembers users deeply, turning a utility into a companion, driving unprecedented retention rates.
- **Consistency → Trust:** A built-in Homeostatic governor ensures the AI does not hallucinate wild persona shifts. It reacts predictably to environmental and emotional vectors, fostering deep user trust.
- **State → Engagement Depth:** By tracking internal states (mood, energy, attachment), DRIFT behaves temporally. A user interacting with DRIFT feels a progression of relationship, skyrocketing session length and engagement depth.
- **The Forge → Rapid, Safe Iteration:** DRIFT is paired with our isolated testing apparatus, The Forge. We can scientifically ablate, perturb, and deploy cognitive updates faster and safer than competitors relying on manual vibe checks.

DRIFT is not just a prompt wrapper—it is a falsifiable, persistent state engine that gives AI an inner life.

📄 **[Read the scientific paper and methodology →](https://doi.org/10.5281/zenodo.20350249)**

---

## Architecture

```
User Input
    │
    ▼
Security Scan ──── blocked? → refusal
    │
    ▼
Prompt Assembly (CognitiveOrchestrator)
    │
    ├── Being (mood, energy, curiosity, attachment)
    ├── Homeostasis (needs: rest, connection, purpose, stimulation)
    ├── Shadow (suppressed archetypes, integration level)
    ├── Global Workspace (spotlight → active → preconscious → archived)
    ├── Hive Mind (consensus threads, council votes)
    ├── Memory (semantic + episodic, DMU re-ranked)
    └── Logic Chain (previously-tried approaches)
    │
    ▼
LLM Router
    ├── Gemini (primary)
    ├── Groq / Kimi (cloud fallback)
    └── Ollama (local offline fallback)
    │
    ▼
Response + State Update
```

### Layer map

| Layer | Modules | Purpose |
|-------|---------|---------|
| **Interface** | `interfaces/api.py`, `interfaces/main.py`, `interfaces/web_app.py` | REST API, CLI loop, Web UI |
| **Orchestration** | `core/cognitive_orchestrator.py`, `core/brain.py` | Prompt assembly, LLM routing, tool execution |
| **Cognition** | `core/being.py`, `core/homeostasis.py`, `core/shadow.py` | Emotional state, physiological needs, Jungian shadow |
| **Consciousness** | `core/global_workspace.py` | Tiered attention: spotlight → active → preconscious bands → SQLite archive |
| **Distributed Cognition** | `hive_mind/`, `core/hive/`, `core/coordination.py` | Consensus engine, council of voices, Elysium deliberation |
| **Memory** | `core/memory.py`, `core/unified_memory.py`, `core/logic_chain.py` | ChromaDB semantic recall, episodic store, reasoning traces |
| **Safety** | `core/security_defense.py`, `core/guardrails.py` | Input scanning, scope rails, secret scrubbing |

---

## Key Subsystems

### Global Workspace (Tiered Attention)
Each cycle all active items compete by salience. The winner becomes the **spotlight** (what the bot is consciously attending to). Runners-up fill the **active workspace** and feed directly into the prompt. Items below the active threshold are retained in **preconscious bands** (strong / moderate / faint / trace). Anything below the archive threshold is logged to SQLite and evicted.

```
Spotlight (rank 1) → most salient item right now
Active (ranks 2–5) → consciously available, included in prompt
Preconscious bands  → retained below threshold, not yet forgotten
Archived            → logged to SQLite, evicted from memory
```

### Hive Mind (Distributed Cognition)
A lightweight consensus engine for multi-voice deliberation. Nodes propose thoughts, cast votes, and resolve threads. Safety vetoes are hardwired — any proposal touching backdoors or guardrail bypasses is immediately `TABLED`.

```python
# What happens when you /hive propose ...
engine.propose(msg)                          # open a thread
engine.vote(thread_id, "lantern-4", "BLOCK") # safety node votes
engine.resolve(thread_id, Resolution.TABLED) # thread closed
```

The **Elysium** engine (in `core/hive/`) runs deeper async deliberations with a persistent Nexus self-model and 7 council voices (Aura, Logic, Meme, Vibe, Ethos, Pulse, Nexus).

### Shadow (Jungian Integration)
Suppressed archetypes accumulate depth over time. High-stress turns can surface them into conscious awareness. The bot can run **active imagination** dialogues to integrate shadow content. Unintegrated archetypes influence tone through `format_prompt_snippet`.

### Homeostasis
Five tracked needs (rest, connection, purpose, stimulation, safety) decay over time and create pressure on the bot's behavior. Allostatic load and a `crisis_mode` flag affect response tone. Decay rates are configurable via env vars.

---

## Development Status & Functional Coverage

PHI // DRIFT is an active research project. While the core cognitive architecture is functional, certain subsystems use **production-ready stubs** or **local mocks** to ensure stability across different environments. 

For a transparent record of the challenges, syntax crises, and methodology errors we've encountered, see **[MISHAPS.md](./MISHAPS.md)**.

### Stubs & Mocked Functions

The following components are known to be placeholders or local mocks in the current release:

| Component | Location | Status | Purpose |
|-----------|----------|--------|---------|
| **Generative SDK** | `core/brain.py` | **Mocked** | Falls back to `local_genai_mock.py` if official API keys are not provided. |
| **Unified Memory** | `adapters/memory_adapter.py` | **Stub** | `query_all()` is currently a placeholder for cross-layer search (Working/Semantic/Shared). |
| **Cognitive Factory** | `core/cognitive_factory.py` | **Stub Generator** | Generates `TODO` placeholders in `cycle()` and `format_prompt_snippet()` for new modules. |
| **Retry Wrapper** | `core/retry_wrapper.py` | **Mocked** | Contains a placeholder `generate_with_retry` used during isolation testing. |
| **System Prompts** | `core/safe_math_integration.py` | **Placeholder** | Uses "SYSTEM PROMPT PLACEHOLDER" for math-specific safety gating in certain modes. |

> **Note on "Production Mocks":** These are not "missing" features but intentional architectural boundaries that allow the system to operate in a "degraded" but stable state when external dependencies are unavailable.

---

## Getting Started

### One-command install plan

Run:

```bash
anchor install laptop
```

or for a droplet:

```bash
anchor install droplet --public-url http://<droplet-ip>:8767/anchor
```

### Fresh VM bootstrap

```bash
git clone https://github.com/timeless-hayoka/drift.git
cd drift
./scripts/bootstrap_anchor.sh
```

That script creates `.venv`, installs the package in editable mode, runs `anchor setup`, checks `anchor doctor`, verifies `anchor status` and `anchor release`, runs the focused smoke tests, and proves the main web routes answer.

> Torch (~2 GB) is required for local embeddings and the full server. On CPU-only machines:
> ```bash
> pip install torch --index-url https://download.pytorch.org/whl/cpu
> ```

### Optional manual run

```bash
# CLI chat loop
python interfaces/main.py

# REST API  →  http://127.0.0.1:8765
uvicorn drift.interfaces.api:app --host 127.0.0.1 --port 8765 --reload

# Web UI  →  http://127.0.0.1:5000
python interfaces/web_app.py
```

---

## Commands

| Command | What it does |
|---------|-------------|
| `/mode companion\|engineer\|critic\|coach\|clarity\|researcher\|bughunter\|quiet\|drift` | Switch persona mode |
| `/memory <query>` | Search long-term memory |
| `/memory learn <name>: <desc>` | Store a concept |
| `/hive` | Show Hive Mind status and active consensus threads |
| `/hive propose <thought>` | Submit a thought for collective review |
| `/hive nexus decide <goal>` | Run Elysium council deliberation on a goal |
| `/hive reflect` | Trigger a council reflection |
| `/hive council status` | Show each council voice's energy and win count |
| `/workspace status` | Show the conscious attention workspace |
| `/workspace focus <content>` | Move spotlight to a specific item |
| `/workspace reflect` | Generate a metacognitive reflection |
| `/chain list` | Show active reasoning chains |
| `/chain mark <query> fail` | Mark an approach as dead-end |
| `/security status` | Show security scanner state |
| `/security test <text>` | Scan arbitrary text |
| `/health` | Check model, memory, and system status |
| `/reset` | Clear session history and brain context |
| `/todo add <title>` | Add a goal |

---

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/health` | GET | System health, memory count, turn count |
| `/api/chat` | POST | Single-turn chat |
| `/api/chat/stream` | POST | Server-sent events streaming |
| `/api/tools` | GET | Available tool inventory |
| `/api/observer` | GET | Full real-time cognitive state (being, needs, shadow, workspace, DII) |
| `/api/dii` | GET | Dynamic Integration Index trend |
| `/api/phi` | GET | PHI council status and subjective state |
| `/api/hive` | GET | Hive Mind status |
| `/api/command` | POST | Execute a slash command |

---

## Tests

```bash
# Full suite (requires torch)
pytest tests/ -q

# Without torch
pytest tests/ -q \
  --ignore=tests/test_bot.py \
  --ignore=tests/test_stress.py \
  --ignore=tests/test_upgrade_infrastructure.py

# Specific suites
pytest tests/test_shadow.py tests/test_elysium.py tests/test_temporal.py -v
```

**CI checks:** lint (ruff), typecheck (mypy), test (pytest) — all green on every push.

---

## Ablation Results (May 2026)

6-condition test measuring the impact of removing each subsystem. Run on live Ollama `qwen3:4b` (CPU).

| Condition | Change | Finding |
|-----------|--------|---------|
| A — No Council | Elysium stubbed | Latency neutral — council is background-only |
| B — No Shadow | Shadow tick disabled | Latency neutral — shadow operates via cache |
| C — No Homeostasis | Needs flattened | Latency neutral — state still initialized |
| D — Cosine-only RAG | DMU re-ranking removed | **Prompt ↓ 221 chars (7.7%)** — DMU injects meaningful context |
| E — Local LLM only | Cloud providers off | Baseline latency |
| F — Full stack | No changes | 3095-char avg prompt, 62.9s latency |

Removing DMU re-ranking (D) is the most measurable signal — the 221-character gap is the difference between simple cosine top-N and salience-weighted dynamic recall.

> Re-run: `python tests/ablation_suite.py --conditions A,B,C,D,E,F --prompts 50 --live`

---

## Citation

> **PHI // DRIFT: A Homeostatic Cognitive Architecture for Persistent, State-Aware AI Companionship**
>
> Zenodo: [https://doi.org/10.5281/zenodo.20350249](https://doi.org/10.5281/zenodo.20350249)
> PDF: [DRIFT_paper_v4.pdf](https://zenodo.org/records/20350249/files/DRIFT_paper_v4.pdf)

---

## License

Apache 2.0 — see [`LICENSE`](LICENSE).
