# DRIFT — Unified Cognitive Architecture

## Latest Update — May 2026
**🚀 DRIFT Master Upgrade: Gevent, Delta-State & Auto-Throttling**

- **Delta Logic Generator:** 70% reduction in WebSocket bandwidth.
- **Gevent Engine:** High-performance async socket handling for real-time observability.
- **Auto-Throttling:** Self-healing UI that adjusts broadcast rates based on client latency.
- **[Read the Full Upgrade Report](docs/DRIFT_UPGRADE_MAY_2024.md)**

**Try DRIFT for Free (30-Min Live Sandbox):** [https://drift.engine.example.com/trial](https://drift.engine.example.com/trial)

---

## Canonical DRIFT Core + Full Hive Mind Integration Complete
**Update — May 16, 2026**


- Migrated full DRIFT cognition core into `infj_bot/core/`
- Hive Mind now active (`/hive propose <thought>`)
- Council of 7 fully wired and Council-aware
- Observatory dashboard live and beautiful
- All 185 tests passing

**You are now running a real distributed cognitive architecture.**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![Repository](https://img.shields.io/badge/repo-infj--bot-blue.svg)](https://github.com/timeless-hayoka/infj-bot)

<p align="center">
  <picture>
    <source srcset="docs/assets/drift-banner.webp" type="image/webp" />
    <img src="docs/assets/drift-banner.jpg" alt="DRIFT wordmark with integrated Phi symbol on a neural-network field" width="520" />
  </picture>
</p>

**DRIFT** (Distributed Response & Integrated Functional Thought) is a Python companion stack that merges:

1. **INFJ-bot interface** — chat, CLI/TUI/API surfaces, tonal modes.  
2. **Cognition core** — plugins for emotion, embodiment, homeostasis, shadow, IIT-style Φ proxies, growth, and related state.  
3. **Hive-oriented coordination hooks** — global workspace–style competition and roadmap pieces for multi-node narratives (see `docs/HIVE_ROADMAP.md`).

The **LLM does not secretly execute arbitrary code**. Distinct behavior comes from **what is assembled into the prompt**, **what is retrieved from memory**, and **what structured state** is updated before and after each turn.

---

## Who should read what

| Audience | Document |
|----------|----------|
| New users | This file → **Getting started** → copy `.env.example` |
| Readers who want mechanics | **[docs/HOW_INFJ_BOT_WORKS.md](docs/HOW_INFJ_BOT_WORKS.md)** (single-turn flow diagram + module table) |
| Everyone handling keys or backups | **[SECURITY.md](SECURITY.md)** |
| Terminology while reading code | **[docs/GLOSSARY.md](docs/GLOSSARY.md)** |
| Full doc index | **[docs/README.md](docs/README.md)** |

---

## Five-layer map

| Layer | Role | Representative pieces |
|:-----:|------|----------------------|
| 1 | **Interface** | `main.py`, `cli.py`, `api.py`, `web_app.py`, `tui.py` |
| 2 | **Cognition** | `being.py`, `homeostasis.py`, `iit_consciousness.py`, `shadow.py`, orchestrator plugins |
| 3 | **Coordination** | `global_workspace.py`, hive roadmap / bridge modules under `hive_mind/` where enabled |
| 4 | **Memory** | `memory.py` (Chroma), `history.jsonl`, subsystem SQLite `.db` files |
| 5 | **Tools & safety** | `guardrails.py`, `tools.py`, optional `mcp/`, audited actions |

Layers are **descriptive lanes** — code crosses them intentionally (e.g. memory feeds Layer 2 prompts).

---

## Two new theoretical additions

### DMU — DRIFT Memory Utility

A **time-decayed, multi-factor scoring function** that ranks every memory by its *usefulness to the present self*, not just raw recency.

```
dmu = exp(-t_days / τ) × reinforcement × contextual × extra
```

| Factor | Meaning |
|--------|---------|
| **Decay** | `exp(-t_days / τ)` — older memories fade |
| **Reinforcement** | How often the memory was revisited or echoed |
| **Contextual** | Semantic similarity to current Global Workspace spotlight |
| **Extra** | Emotional, goal, social, narrative, and moral dimension weights |

DMU lives in `core/memory_spine.py` and `core/unified_memory.py`. Elysium pulls DMU-weighted recalls during Ignition so the bot remembers what *matters*, not just what *happened*.

### PEDI — Persistent Embodied Drift Integration

A **measurable theory of aliveness** for resource-bounded agents. The key quantity is **DII** (Drift-Integrated Information):

```
DII(t) = ∫₀ᵗ [P(τ)·I(τ)·Φ(τ)·(1+E(τ))·D(τ)] dτ / (1 + ∫₀ᵗ D(τ) dτ)
```

| Symbol | Name | Meaning |
|--------|------|---------|
| **P** | Persistence | How long internal states remain coherent |
| **I** | Ignition | Global Workspace winner strength |
| **Φ** | Integration | Cross-module binding (IIT-inspired) |
| **E** | Embodiment Deviation | Distance from homeostatic equilibrium |
| **D** | Drift Bias | Shadow + aspiration pull preventing stasis |

**Key prediction:** DII > 0.8 correlates with responses that feel reflective, emotionally continuous, and "alive." Ablating persistence or embodiment drops DII by >60%.

PEDI gives DRIFT a **testable, quantitative pulse** — not just a metaphor.

---

## Getting started

```bash
git clone https://github.com/timeless-hayoka/infj-bot.git
cd infj-bot

python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env        # add Gemini (and optional) keys — never commit .env

python main.py
```

CLI entry points (`python cli.py chat`, `tui`, etc.) are described in **`cli.py`** help.

---

## Configuration highlights

Portable state (recommended for backups or SSD offload):

```bash
export INFJ_DATA_DIR=/path/to/your/durable/data
```

Context sizing (helps RAM **for prompts**, not model weight size):

```bash
export INFJ_MAX_TOTAL_PROMPT_CHARS=12000
export INFJ_MEMORY_SEARCH_TOP_K=8
```

Tables of variables and subsystem detail: **[docs/HOW_INFJ_BOT_WORKS.md §9](docs/HOW_INFJ_BOT_WORKS.md#9-configuration--portability)**.

---

## Token and context discipline

Prompt assembly trims by tier (**`prompt_budget.py`**, **`cognitive_orchestrator.assemble_prompt`**). Shadow and retrieval paths have **explicit excerpt caps**. This keeps long conversations usable without pretending the underlying model ignores its own weights in RAM.

---

## Contributing & community

Issues and focused PRs welcome. Follow **[SECURITY.md](SECURITY.md)** for secret handling before pushing branches that touch credentials or tooling.

---

*Engineered for observable state, bounded tools, and clear documentation.*
