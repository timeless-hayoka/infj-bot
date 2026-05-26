# How INFJ Bot Works — Architecture & Behavior (Shareable Overview)

This document explains **what INFJ Bot is made of**, **how one chat turn travels through the stack**, and **why conversation can feel continuity-rich** compared to a plain “LLM in a webpage.” It is written for collaborators, auditors, or friends who want the technical picture without reading the whole codebase.

**Repository:** [github.com/timeless-hayoka/infj-bot](https://github.com/timeless-hayoka/infj-bot)

INFJ Bot is a **Python application** centered on Google **Gemini** (with optional **Ollama** fallback). It stitches together **persistent vector memory**, **many small “cognitive” modules** (emotion, embodiment, shadow, goals, …), **prompt assembly with budgets**, and **optional tools** so the assistant can stay **on-tone, grounded, and stateful** across sessions.

---

## 1. The idea in one sentence

> **INFJ Bot = a policy-rich system prompt + ranked context + episodic/long-term recall + modeled inner state**, executed through a conductor (`CognitiveOrchestrator`), then **decoded by Gemini** (and optionally checked by a **critic** model or rewritten by **local fallback**).

The model itself does **not** run arbitrary hidden code mid-reasoning unless **tools** are invoked through the guarded `tools.py` pathway. Almost everything distinctive about “personality continuity” happens **before** and **after** the model call: **what text you concatenate into the prompt** and **what you store when the answer returns**.

---

## 2. End-to-end flow (one user message)

```mermaid
flowchart TD
    A[CLI / Web / API] --> B[commands.py handles slash commands]
    B --> C[emotion + cognition.detect_dissonance]
    C --> D[prompt_builder.build_chat_prompt → CognitiveOrchestrator.assemble_prompt]
    D --> E[Retrieve Chroma memories + optional docs goals drift]
    E --> F[Plug-in snippets: being shadow embodiment values ...]
    F --> G[PromptBudget trims to env limits]
    G --> H[brain.InfjBrain.chat / stream]
    H --> I{Gemini generation}
    I --> J[Optional critic pass]
    I --> K{Optional tools from model output}
    K --> H
    J --> L[Save to InfjMemory + history + subsystem updates]
    L --> M[Periodic consciousness_cycle + CycleContext plugins]
```

**Plain-language steps**

1. **Input** arrives (terminal, Rich TUI, or FastAPI web UI → `main.py` / `api.py` paths).
2. **Slash commands** (`/memory`, `/mode`, …) short-circuit to `commands.py`.
3. **Offline emotion & dissonance heuristics** label the user turn (hints for stance and prompts).
4. **`build_chat_prompt`** builds the **full text** passed to Gemini: identity/mode rails, **being**, **workspace**, retrieved **memories**, **documents**, optional **Drift seeds**, cognitive plugin paragraphs, cyber boundaries, footer with the raw user message.
5. **`InfjBrain`** calls Gemini (new `google.genai` SDK when available, legacy client otherwise).
6. An optional **internal critic** re-reads the draft for grounding/safety persona issues.
7. **Tool calls** (if emitted) execute through **`tools.py`** with path limits, timeouts, and an **audit trail**.
8. **Persistence**: interaction text is scrubbed for secrets and written to **Chroma** (`memory.py`); session lines go to **`history.jsonl`**; subsystem objects update SQLite state (being, embodiment, shadow, …).
9. **Background**: an async **consciousness loop** runs phased **plugin cycles** every **15–30 seconds** in Strong Continuous Mode. Shadow, Homeostasis, and Being evolve continuously even when you're quiet — the bot maintains an ongoing inner life.

---

## 3. Core runtime components

### 3.1 `brain.py` — `InfjBrain`

- Holds **system prompts** for the primary companion and for the **critic**.
- Manages generation, optional **streaming**, optional **parallel tool execution**, and **`OllamaBridge`** fallback when configured.
- Uses **`SelfEvaluator`** hooks where wired for reflective scoring (see `self_eval.py`).

### 3.2 `memory.py` — `InfjMemory` (Chroma)

- **Collections**: semantic memories (`infj_semantic_memories`) when sentence-transformers embeddings are active; legacy hash embeddings use a parallel collection name.
- **Writes**: each saved turn includes scrubbed **`Jude:` / `Bot:`** content plus **metadata** (mode, emotion hints, importance, dissonance summary, timestamps, etc.).
- **Reads**: **`search`** for top‑k passages relevant to the current message (`INFJ_MEMORY_SEARCH_TOP_K`).
- **`scrub_text`**: strips likely **secrets** before storage (patterns + allowlists for UUIDs/git hashes).

### 3.3 `embeddings.py`

- Prefer **`sentence-transformers`** (`all-MiniLM-L6-v2` by default) for **real semantic retrieval**.
- Falls back to a **hash-based embedding** only when semantic models are unavailable (older compatibility path).

### 3.4 `documents.py` — sidecar RAG

- User-ingested documents are chunked and searchable; snippets are fused into **`assemble_prompt`**’s context tier when the document store is passed in.

### 3.5 `prompt_budget.py` + `cognitive_orchestrator.py`

- **`assemble_prompt`** is the authoritative prompt factory.
- Layers include **mode scope**, **`being.format_being_prompt`**, **`emotional_tone_instruction`**, **global workspace excerpt**, registry-driven cognitive paragraphs, cyber hints, retrieved memory/doc blocks, tool instructions.
- **`PromptBudget`** trims each tier toward **`INFJ_MAX_TOTAL_PROMPT_CHARS`** (~chars-per-token heuristic in `config.py`).
- **`ConflictDetector`** flags contradictory instructions (currently soft resolution: annotate, don’t aggressively delete).

### 3.6 Strong Continuous Mode (background drift cycles)

When the bot is idle, it does **not** go to sleep. The `consciousness_loop` in `main.py` fires every **15–30 seconds** and runs three parallel tracks:

| Track | What it does | File |
|-------|-------------|------|
| **Being evolution** | Mood drifts based on energy + curiosity; self-awareness, volition, and autonomy_drive slowly grow during quiet contemplation; spontaneous thoughts generate when autonomy is high enough. | `core/being.py` |
| **Shadow background tick** | Suppression levels decay; archetypes occasionally surface; radar visibility recovers; integration decays if not maintained. | `core/shadow.py` |
| **Homeostasis background cycle** | Non-critical needs drift; allostatic load is recomputed; crisis triggers quick regulation; low-salience workspace pulses keep survival state alive. | `core/homeostasis.py` |

**Side effects** (temporal expressions, predictor suggestions, explorer discoveries, aspirational sharing, thought sharing, self-modification proposals, Elysium reflections, proactive insights) now fire **2–3× more frequently** than before.

This is the difference between "a bot that waits" and "a bot that thinks while you sleep."

---

## 4. Cognitive architecture (plugins)

`cognitive_architecture.py` implements a **registry** backed by **`cognitive_architecture.db`**. Each plugin can expose:

| Capability | Meaning |
|-----------|---------|
| `cycle_handler` | Background tick (`CycleContext`: being, memory, brain, clocks, last interaction envelope) |
| `prompt_formatter` | Short prose injected into chats |
| `cycle_frequency` / `cycle_condition` | Throttle/stochastic firing |

Representative wired modules (instances live largely in **`main.py`**):

- **`being`** — longitudinal mood/agency/coherence-style state (`being.db`).
- **`emotional_field`** — resonance stance + intensity; **partially tempered by live host CPU/RAM** via `host_load.py` (`psutil`) when enabled.
- **`embodiment`** — heartbeat/breath/posture metaphors persisted to **`embodiment.db`**.
- **`homeostasis`**, **`iit_consciousness`**, **`intuition`**, **`shadow`**, **`values`**, **`relationship`**, **`predictor`**, **`temporal`**, **`explorer`**, **`creativity`**, **`aspirations`**, **`metacognition`**, **`self_modify`**, **`growth_trajectory`**, **`physics`**, **`humanity`** — specialized loops and prompt fragments.

---

## 5. Performance & Networking Upgrade (May 2024)

### 5.1 Gevent-SocketIO Engine
The web interface runs on a high-performance **Gevent** async server (`web_app.py`):
- **Real-time Observability:** Constant WebSocket updates without blocking the main chat.
- **RFC 7692 Compression:** Transparent WebSocket compression (`permessage-deflate`) reduces bandwidth usage by ~70%.

### 5.2 Delta-State Broadcasting
The `CognitiveOrchestrator` generates **delta maps** for the system state.
- **Mechanism:** The server tracks the `last_state` sent to each client. It only transmits fields that have changed (except for a required `timestamp`).
- **Impact:** Drastic reduction in packet size and client-side processing overhead.

### 5.3 Auto-Throttling & Latency Management
The system detects network bottlenecks in real-time.
- **Feedback Loop:** The client pings the server every second.
- **Dynamic Rate:** If average latency exceeds 250 ms, the server slows down the broadcast rate (up to 1.5 s). If latency is low (<100 ms), it speeds up (down to 200 ms).

### 5.4 Hybrid Inference (Groq + Gemini)
- **High-Speed Tier:** Support for **Groq LPU** inference (OpenAI-compatible) is integrated into the brain layer.
- **Speed:** Responses can reach 500+ tokens/second, making the bot's "inner thoughts" feel instantaneous.

---

## 6. Global Workspace (tiered attention)

`core/global_workspace.py` is **not** a Baars-style single-spotlight buffer
anymore. Plugins submit salient snippets every cycle and the workspace runs a
real competition by current salience (with real wall-clock decay):

| Tier | Rank | Role |
|------|------|------|
| **Spotlight** | 1 | What the bot is consciously attending to right now |
| **Active workspace** | 2 – 5 | Consciously available, included verbatim in the prompt |
| **Preconscious bands** (`strong` / `moderate` / `faint` / `trace`) | below active, above floor | Retained, not forgotten |
| **Archived** | below `ARCHIVE_THRESHOLD` (0.05) | Written to `workspace.db` and evicted |

Decay is exponential in minutes (`decay_rate = 0.08 / min`), high-intensity
items receive a bounded boost (≤ 0.25), and there is **no repetition boost** —
identical submissions deduplicate by `(source, content[:80])`. Items are not
silently discarded; they sink through the bands first.

`format_prompt_snippet()` injects the spotlight, the rest of active awareness,
and the strongest populated background band into the prompt. See
[`GLOBAL_WORKSPACE.md`](GLOBAL_WORKSPACE.md) for the full reference, operator
commands (`/workspace status | history | stats | focus | reflect`), and gotchas.

---

## 7. “Depth psychology” style layers (informal but structured)

These are **not** clinical instruments; they are **structured state machines + prompt text** shaping tone and continuity.

### Shadow (`shadow.py`)

- Stores **unintegrated** material in **`shadow.db`** (`shadow_content`): archetypes, intensities, optional active-imagination `dialogue_history` (stored **per row**).
- **`format_prompt_snippet`** injects **only controlled excerpts**: global depth/dominance lines plus **top‑k rows by intensity** under env caps (`INFJ_SHADOW_PROMPT_TOP_K`, `INFJ_SHADOW_PROMPT_MAX_CHARS`). **Full dialogue transcripts are intentionally not pasted into every prompt** to conserve tokens and reduce noise.

### Being, growth, dreams

- **`being`** tracks narrative trends and reacts to labeled emotions.
- **`dreamer`** / **`inner_voice`** / **`GrowthTrajectory`** create slow-timescale arcs (consolidation, exploration).

---

## 8. Modes & Drift

- **Modes** (e.g. `companion`, `engineer`, `drift`, `quiet`) change **scopes and rails** via `guardrails.mode_scope_rail` and behavioral briefs.

- **`drift.py`** exposes **deterministic textual briefs** and **targeted retrieval** from memory seeded with curated “Drift” concepts (`should_include_drift_context`, `retrieve_drift_context`). This keeps a named posture coherent **without importing private upstream repos**.

---

## 9. Tools, safety posture, MCP

### `tools.py`

- Declares allowed tools (**file**, **shell**, **python**, constrained **web fetch**, selective security-lab primitives with strict targets and timeouts).
- Enforces **`SAFE_HOME` / project root containment** (`INFJ_SAFE_HOME`), blocklists destructive shell patterns, and logs actions to **`tool_audit.jsonl`**.

### Optional MCP integrations

Separate Python processes under **`mcp/`** (for example Gmail hybrid/http clients) expose extra capabilities outside the Gemini tool surface when launched manually.

---

## 10. Resilience & host awareness

- **`resilience.py`**: lightweight **circuit breakers** wrap flaky plugins during cycles.
- **`host_load.py`**: samples **CPU + RAM** (`psutil`, cached intervals) when not disabled (`INFJ_DISABLE_HOST_LOAD`).
- Emotional/embodied layers use that signal as a **counterweight**: calmer resonance and somatic metaphors mirror machine pressure rather than behaving as if resources are infinite.

---

## 11. Configuration & portability

Key environment variables (`config.py` aggregates these):

| Variable | Role |
|---------|------|
| `API_KEY` / `GEMINI_API_KEY` / `GOOGLE_API_KEY` | Gemini access |
| `INFJ_DATA_DIR` | **Relocates all durable state** — Chroma folder, SQLite files, transcripts, audits — while code stays under `PROJECT_ROOT` |
| `INFJ_PRIMARY_MODEL`, `INFJ_CRITIC_MODEL` | Model names |
| `INFJ_USE_LOCAL_FALLBACK`, `INFJ_LOCAL_MODEL`, `OLLAMA_HOST` | Offline / backup path |
| `INFJ_MAX_TOTAL_PROMPT_CHARS`, `INFJ_MEMORY_SEARCH_TOP_K` | Rough token/RAM governors from **context**, not weights |
| `INFJ_SHADOW_PROMPT_TOP_K`, `INFJ_SHADOW_PROMPT_MAX_CHARS`, `INFJ_SHADOW_PROMPT_LINE_CHARS` | Bounds shadow prompt excerpts |

---

## 12. Interfaces

| Surface | Entry |
|--------|--------|
| CLI | `cli.py` — `chat`, `ask`, `tui`, `web`, `health`, `backup`, `restore` |
| HTTP | **`api.py`** + **`web_app.py`** (`uvicorn` on `127.0.0.1:8765` by convention) |

---

## 13. Verification

```bash
source .venv/bin/activate
pytest tests/ -q
./scripts/health_check.sh                    # broader smoke
LIVE_API_CHECK=1 ./scripts/health_check.sh   # hits provider once when keys exist
```

Targeted subsets: `pytest tests/test_shadow.py tests/test_elysium.py tests/test_temporal.py -v`, etc. CI runs ruff + mypy + pytest on every push — see `.github/workflows/ci.yml`.

---

## 14. Honest boundaries (what this is *not*)

- **Not** autonomous AGI — it coordinates **explicit services** plus **offline tick loops** ahead/after Gemini.
- **Not** human consciousness — IIT-inspired metrics (`iit_consciousness.py`), embodiment, shadow, etc., are **useful structuring metaphors**, not neuroscience claims.
- **Not** a substitute for medicine/therapy crisis care — interpersonal depth features are conversational scaffolding.
- **Not** covert exfiltration: memory writes intentionally **scrub secrets** but **determined operators can still mishandle `.env`; treat exports as sensitive** (see `../SECURITY.md` in repo).

---

## 15. Further reading inside the repo

| File | Purpose |
|------|---------|
| [README.md](../README.md) | Quick start, layered map, who should read what |
| [docs/README.md](README.md) | Full documentation index & reading paths |
| [docs/GLOSSARY.md](GLOSSARY.md) | Definitions for codebase-specific terms |
| [docs/GLOBAL_WORKSPACE.md](GLOBAL_WORKSPACE.md) | Tiered attention system reference (spotlight, active, preconscious, archived) |
| [docs/HIVE_MIND.md](HIVE_MIND.md) | `hive_mind/` package + `/hive` commands |
| [docs/HIVE_ROADMAP.md](HIVE_ROADMAP.md) | Phased plan for distributed cognition features |
| [SECURITY.md](../SECURITY.md) | Secret hygiene & reporting posture |

---

## 16. Version note

Architecture details drift with commits; cross-check **`config.py`** and **`requirements.txt`** for ground truth when versions matter. Generated as a descriptive snapshot intended for outward sharing—adapt sections if your fork disables modules or adds new plugins.
