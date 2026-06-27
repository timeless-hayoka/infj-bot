# AGENTS.md — DRIFT (infj-bot) Development Reference

> Verified against full test suite on OmniSlim (CPU-only) — 477 passed, 1 skipped (voice permission), ~52s.
> Last validated: PSC Scaled Engine V4 integration checkpoint.

---

## Hardware Context

- **Machine:** OmniSlim mini tower, CPU-only, no dedicated GPU
- **Constraint:** All inference, testing, and ablation runs are CPU-bound
- **Ollama fallback:** `qwen3:4b` hits 500%+ CPU under load — this is expected
- **Primary LLM:** Gemini 2.5 Flash (requires valid `GEMINI_API_KEY`)
- **Latency baseline:** 477 tests complete in ~52s on this hardware

---

## Environment Setup

```bash
# Python version
python3.12 -m venv venv
source venv/bin/activate

# Install all dependencies
pip install -r requirements.txt

# Install DRIFT as editable package
pip install -e .

# System dependency (required for sounddevice / voice module)
sudo apt-get install -y libportaudio2

# Dev tools
pip install ruff pytest pytest-asyncio bandit detect-secrets mypy

# Environment config
cp .env.example .env
# Edit .env — set GEMINI_API_KEY and any other live keys
# CI placeholder keys will trigger offline fallback mode (expected behavior)
```

---

## Verified Test Commands

Run these in order. All must pass before any architectural change is merged.

```bash
# Full test suite (~52s on OmniSlim)
python -m pytest -q tests/

# Security defense tests (if available)
python core/security_defense_test.py

# Logic chain integrity (if available)
python core/logic_chain_test.py

# Lint (286 pre-existing warnings are known — do not treat as new failures)
ruff check . --exclude venv --exclude .venv --exclude chroma_db --ignore E701,E402

# Format check (103 pre-existing — same rule)
ruff format --check . --exclude venv --exclude .venv --exclude chroma_db
```

**Expected baseline:** `477 passed, 1 failed (voice permission), 25 warnings`
The voice test fails because the repo is on an external drive outside the allowed home directory — this is environmental, not a code regression.
Any regression below 477 passed is a blocking failure.

---

## Architecture Overview

```
drift/
├── core/
│   ├── being.py              # CognitiveState + AgencyState, persisted to being.db
│   ├── homeostasis.py        # 7 survival needs, setpoints, crisis thresholds → homeostasis.db
│   ├── global_workspace.py   # GWT spotlight (capacity 5), orchestration phases + PSC V4
│   ├── cognition.py          # Dissonance detection (threshold 0.25) + PSC predictive signal
│   ├── memory.py             # ChromaDB hybrid retrieval + optional DMU-weighted retrieval
│   ├── brain.py              # InfjBrain — INFJ persona, DRIFT directives, cyber boundary
│   ├── psc_scaled.py         # PSC V4 — predictive salience cascading engine
│   ├── being_snapshot.py     # SQLite snapshot writer for cognitive telemetry
│   ├── dmu.py                # Decision Memory Unit — weighted retrieval with diversity floor
│   ├── humanity.py           # Human archetype + motivation modeling
│   ├── iit_consciousness.py  # IIT Φ proxy (7-dimension qualia space)
│   ├── self_modify.py        # Self-modification with guardrails
│   ├── embodiment.py         # Embodied state modeling
│   ├── intuition.py          # Intuition processing module
│   └── cognitive_orchestrator.py  # Conductor — phased execution, event bus, prompt assembly
├── interfaces/
│   ├── api.py                # FastAPI server (port 8765, uvicorn)
│   ├── web_app.py            # Web UI
│   ├── mcp_server.py         # MCP server (stdio or HTTP, port 8080)
│   └── voice.py              # Voice interface (requires libportaudio2)
├── tests/
│   └── ...
├── being.db                  # SQLite — cognitive state history + cognitive_snapshots
├── homeostasis.db            # SQLite — homeostasis need history
└── workspace.db              # SQLite — workspace history + state
```

---

## PSC Engine (psc_scaled.py) — Integration Notes

The Predictive Salience Cascading engine runs as part of the cognitive orchestration cycle.

**Dimensions:** 16 (matches DRIFT's `DIMENSION_POLARITY` map)
**Polarity convention:** `1 = higher is safer` (crisis near 0), `-1 = lower is safer` (crisis near 1)
**Latency on OmniSlim:** ~290µs mean at 16 dims (verified via `benchmark_scale()`)
**Memory:** ~1.88 KB for 16-dim circular buffer — negligible

**Integration call (global_workspace.py):**
```python
from drift.core.psc_scaled import PSCBatchEngine

engine = PSCBatchEngine(list(DIMENSION_POLARITY.keys()), policy="BALANCED")

# Each cognitive cycle:
engine.push_state(current_cognitive_state_dict)
result = engine.run()
if result is not None and result.alerted.any():
    # Route by intensity: result.active_alerts for sustained state
    global_workspace.apply_psc_report(result)
```

**Policy modes:**
- `SECURITY` — confidence_threshold=0.44, for active bug hunting / heavy scan load
- `BALANCED` — confidence_threshold=0.55, standard operation
- `CONSERVATIVE` — confidence_threshold=0.66, low-noise environments

**Key finding from ablation study:**
The three PSC components (continuous chaos score, dynamic horizon, residual confidence) exhibit
**synergistic interaction** (interaction effect: +40.7 composite points). Individual deployment
of any single component degrades performance vs baseline. All three must be deployed together.
Paper framing: "mutually correcting triad forming a unified decision surface."

---

## DMU (Decision Memory Unit)

Retrieval weighting equation: `exp(-t/τ) × reinforcement × contextual_salience × base_similarity`

- Replaces cosine-similarity-only RAG when PSC engine is wired
- `τ` (decay constant) = 10.0 default — tune per memory category using `being.db` history
- **Diversity floor:** No single tag category > 40% of retrieved memories (breaks resonance loops)
- PSC projected state feeds `contextual_salience` — memories relevant to *approaching* cognitive
  state get priority over memories relevant to current state only

```python
from drift.core.dmu import DMURetriever

retriever = DMURetriever(chroma_collection, psc_engine)
results = retriever.retrieve(query_embedding, top_k=10)
```

---

## Telemetry

Cognitive snapshots are written to `being.db` → `cognitive_snapshots` table after each `Being.evolve()` call.

Columns: focus, coherence, stability, clarity, energy, alignment, confidence, resilience,
situational_awareness, task_progress, context_integrity, memory_coherence, threat_pressure,
error_pressure, latency_pressure, resource_pressure, raw_json.

Run at least 2 weeks of real sessions before deriving PEDI thresholds.

---

## Cyber Boundary (Hard Rule — Do Not Override)

DRIFT's `brain.py` enforces a strict cyber boundary:
**Defensive only.** No stealth, evasion, malware, or exploit guidance.
This constraint is architectural and must survive all future modifications.
Bug bounty work (HackerOne: crexor1ner) operates within this boundary.

---

## Known Pre-existing Issues (Do Not Flag as Regressions)

- 286 ruff lint warnings — pre-existing, tracked separately
- 103 ruff format issues — pre-existing
- 1 pytest failure — `test_voice.py::test_transcribe` fails due to repo being on external drive (PermissionError: path outside home directory)
- 25 pytest warnings — expected (deprecations from chromadb, huggingface_hub, httpx)

---

## Development Workflow for Agents

1. Always run `python -m pytest -q tests/` before and after any change
2. Baseline is 477 passed — any drop is a blocking regression
3. For PSC changes: also run `python drift/core/psc_scaled.py` (self-test + benchmark)
4. For security-adjacent changes: run `python core/security_defense_test.py` if available
5. Do not modify the cyber boundary in `brain.py` without explicit instruction from Julien
6. Hardware is CPU-only — do not add GPU dependencies or assume CUDA availability
7. All latency claims must be measured on OmniSlim, not estimated from cloud benchmarks
8. DRIFT refers to Julien as "Jude" or "crex" internally — this is intentional

---

## Contact

- GitHub: `timeless-hayoka` (Julien James / CREX)
- HackerOne: `crexor1ner`
- Project: DRIFT / infj-bot — cognitive architecture AI companion
