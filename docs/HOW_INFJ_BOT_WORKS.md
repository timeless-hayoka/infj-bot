# How INFJ Bot Works — Architecture & Behavior (Shareable Overview)

This document explains **what INFJ Bot is made of**, **how one chat turn travels through the stack**, and **why conversation can feel continuity-rich** compared to a plain “LLM in a webpage.” It is written for collaborators, auditors, or friends who want the technical picture without reading the whole codebase.

**Repository:** [github.com/timeless-hayoka/infj-bot](https://github.com/timeless-hayoka/infj-bot)

INFJ Bot is a **Python application** centered on Google **Gemini** (with optional **Groq**, **Kimi**, and **Ollama** fallbacks). It stitches together **persistent vector memory**, **many small "cognitive" modules** (emotion, embodiment, shadow, goals, …), **prompt assembly with budgets**, and **optional tools** so the assistant can stay **on-tone, grounded, and stateful** across sessions.

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

### 3.1 `brain.py` — `DriftBrain`

- Holds **system prompts** for the primary companion and for the **critic**.
- Manages generation, optional **streaming**, optional **parallel tool execution**, and **`OllamaBridge`** fallback when configured.
- Routes between **Gemini → Groq → Kimi → Ollama** based on `DRIFT_USE_GROQ` / `DRIFT_USE_KIMI` / `INFJ_USE_LOCAL_FALLBACK`.
- Uses **`SelfEvaluator`** hooks where wired for reflective scoring (see `self_eval.py`).
- Generation timeouts and retries are governed by [`retry_wrapper.py`](SHADOW_GOVERNANCE.md#3-coreretry_wrapperpy--dynamic-timeouts--exponential-backoff).

### 3.2 `memory.py` — `DriftMemory` (Chroma)

- **Collections**: semantic memories (`infj_semantic_memories`) when sentence-transformers embeddings are active; legacy hash embeddings use a parallel collection name.
- **Writes**: each saved turn includes scrubbed **`Jude:` / `Bot:`** content plus **metadata** (mode, emotion hints, importance, dissonance summary, timestamps, etc.).
- **Reads**: **`search`** for top‑k passages relevant to the current message (`INFJ_MEMORY_SEARCH_TOP_K`).
- **`scrub_text`**: strips likely **secrets** before storage (patterns + allowlists for UUIDs/git hashes).

### 3.3 `embeddings.py`

- Prefer **`sentence-transformers`** (`all-MiniLM-L6-v2` by default) for **real semantic retrieval**.
- Falls back to a **hash-based embedding** only when semantic models are unavailable (older compatibility path).

### 3.4 `documents.py` — sidecar RAG

- User-ingested documents are chunked and searchable; snippets are fused into **`assemble_prompt`**’s context tier when the document store is passed in.

### 3.5 `global_workspace.py` — tiered attention

The previous Baars-style "spotlight only" workspace was replaced with a real competition model (see [`core/global_workspace.py`](../core/global_workspace.py)):

```
Spotlight    (rank 1)   — most salient item this cycle
Active       (ranks 2–5) — included in the prompt
Preconscious (strong / moderate / faint / trace) — retained below threshold
Archived               — salience < 0.05, logged to SQLite and evicted
```

Each cycle every surviving item competes by `current_salience(now)`, with **real elapsed-time exponential decay** (`decay_rate` per minute) and a capped emotional-intensity boost. Items below the active capacity (default 5) drop into preconscious bands instead of being discarded; only items below `ARCHIVE_THRESHOLD = 0.05` are evicted. The old infinite-broadcast-count salience inflation bug is gone.

### 3.6 `prompt_budget.py` + `cognitive_orchestrator.py`

- **`assemble_prompt`** is the authoritative prompt factory.
- Layers include **mode scope**, **`being.format_being_prompt`**, **`emotional_tone_instruction`**, **global workspace excerpt**, registry-driven cognitive paragraphs, cyber hints, retrieved memory/doc blocks, tool instructions.
- **`PromptBudget`** trims each tier toward **`INFJ_MAX_TOTAL_PROMPT_CHARS`** (~chars-per-token heuristic in `config.py`).
- **`ConflictDetector`** flags contradictory instructions (currently soft resolution: annotate, don’t aggressively delete).

### 3.7 Strong Continuous Mode (background drift cycles)

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
- **`homeostasis`**, **`intuition`**, **`shadow`**, **`shadow_governance`**, **`values`**, **`relationship`**, **`predictor`**, **`temporal`**, **`explorer`**, **`creativity`**, **`aspirations`**, **`metacognition`**, **`self_modify`**, **`growth_trajectory`**, **`physics`**, **`humanity`** — specialized loops and prompt fragments. Integrated-information / Φ telemetry surfaces through `phi_council.py` and the `/glyph` dashboard rather than a dedicated `iit_consciousness.py` module.

---

## 4. Performance & Networking

### 4.1 Gevent-SocketIO Engine
The web interface (`interfaces/web_app.py`) runs on a **gevent** async server. This enables:
- **Real-time Observability:** Constant WebSocket updates without blocking the main chat.
- **RFC 7692 Compression:** Transparent WebSocket compression (`permessage-deflate`) reduces bandwidth usage by ~70%.

### 4.2 Delta-State Broadcasting
`CognitiveOrchestrator` emits **delta maps** for the system state.
- **Mechanism:** The server tracks the `last_state` sent to each client. It only transmits fields that have changed (except for a required `timestamp`).
- **Impact:** Drastic reduction in packet size and client-side processing overhead.

### 4.3 Auto-Throttling & Latency Management
The system detects network bottlenecks in real-time.
- **Feedback Loop:** The client pings the server every second (`latency_ping`).
- **Dynamic Rate:** Broadcast interval is clamped to **[0.2 s, 1.5 s]** and adjusted via the `auto_adjust_rate` SocketIO message.

### 4.4 Hybrid Inference (Gemini + Groq + Kimi + Ollama)
- **Primary:** Google Gemini (`google.genai` SDK preferred, legacy client fallback).
- **High-speed tier:** Groq LPU (OpenAI-compatible) when `DRIFT_USE_GROQ=true`.
- **Moonshot tier:** Kimi (`KIMI_API_KEY`) when `DRIFT_USE_KIMI=true`.
- **Offline tier:** Ollama (`INFJ_USE_LOCAL_FALLBACK=true`), guarded by [`retry_wrapper.py`](SHADOW_GOVERNANCE.md#3-coreretry_wrapperpy--dynamic-timeouts--exponential-backoff).

For full route table see [DEPLOYMENT.md](DEPLOYMENT.md).

---

## 5. "Depth psychology" style layers (informal but structured)

These are **not** clinical instruments; they are **structured state machines + prompt text** shaping tone and continuity.

### Shadow (`shadow.py`)

- Stores **unintegrated** material in **`shadow.db`** (`shadow_content`): archetypes, intensities, optional active-imagination `dialogue_history` (stored **per row**).
- **`format_prompt_snippet`** injects **only controlled excerpts**: global depth/dominance lines plus **top‑k rows by intensity** under env caps (`INFJ_SHADOW_PROMPT_TOP_K`, `INFJ_SHADOW_PROMPT_MAX_CHARS`). **Full dialogue transcripts are intentionally not pasted into every prompt** to conserve tokens and reduce noise.

### Being, growth, dreams

- **`being`** tracks narrative trends and reacts to labeled emotions.
- **`dreamer`** / **`inner_voice`** / **`GrowthTrajectory`** create slow-timescale arcs (consolidation, exploration).

---

## 6. Modes & Drift

- **Modes** (e.g. `companion`, `engineer`, `drift`, `quiet`) change **scopes and rails** via `guardrails.mode_scope_rail` and behavioral briefs.

- **`drift.py`** exposes **deterministic textual briefs** and **targeted retrieval** from memory seeded with curated “Drift” concepts (`should_include_drift_context`, `retrieve_drift_context`). This keeps a named posture coherent **without importing private upstream repos**.

---

## 7. Tools, safety posture, MCP

### `tools.py`

- Declares allowed tools (**file**, **shell**, **python**, constrained **web fetch**, selective security-lab primitives with strict targets and timeouts).
- Enforces **`SAFE_HOME` / project root containment** (`INFJ_SAFE_HOME`), blocklists destructive shell patterns, and logs actions to **`tool_audit.jsonl`**.

### Optional MCP integrations

Separate Python processes under **`mcp/`** (for example Gmail hybrid/http clients) expose extra capabilities outside the Gemini tool surface when launched manually.

---

## 8. Resilience & host awareness

- **`resilience.py`**: lightweight **circuit breakers** wrap flaky plugins during cycles.
- **`host_load.py`**: samples **CPU + RAM** (`psutil`, cached intervals) when not disabled (`INFJ_DISABLE_HOST_LOAD`).
- Emotional/embodied layers use that signal as a **counterweight**: calmer resonance and somatic metaphors mirror machine pressure rather than behaving as if resources are infinite.

---

## 9. Configuration & portability

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

## 10. Interfaces

| Surface | Entry |
|--------|--------|
| CLI | `interfaces/main.py` (chat loop) + `interfaces/cli.py` (`chat`, `ask`, `tui`, `web`, `health`, `backup`, `restore`) |
| Web | **`interfaces/web_app.py`** — Flask + Flask-SocketIO on **gevent**, default port `7860` |
| REST API | **`interfaces/api.py`** — uvicorn on `127.0.0.1:8765` (headless mode) |

The deployable image boots `web_app.py`; the uvicorn API ships as the headless alternative. See [DEPLOYMENT.md](DEPLOYMENT.md) for the full route table and Hugging Face Space contract.

---

## 11. Verification

```bash
source venv/bin/activate
pytest
./scripts/health_check.sh           # broader smoke
LIVE_API_CHECK=1 ./scripts/health_check.sh   # hits provider once when keys exist
```

Targeted subsets: `pytest tests/test_shadow.py tests/test_embeddings.py tests/test_prompt_budget.py`, etc.

---

## 12. Honest boundaries (what this is *not*)

- **Not** autonomous AGI — it coordinates **explicit services** plus **offline tick loops** ahead/after Gemini.
- **Not** human consciousness — IIT-inspired metrics (`iit_consciousness.py`), embodiment, shadow, etc., are **useful structuring metaphors**, not neuroscience claims.
- **Not** a substitute for medicine/therapy crisis care — interpersonal depth features are conversational scaffolding.
- **Not** covert exfiltration: memory writes intentionally **scrub secrets** but **determined operators can still mishandle `.env`; treat exports as sensitive** (see `../SECURITY.md` in repo).

---

## 13. Further reading inside the repo

| File | Purpose |
|------|---------|
| [README.md](../README.md) | Quick start, layered map, who should read what |
| [docs/README.md](README.md) | Full documentation index & reading paths |
| [docs/GLOSSARY.md](GLOSSARY.md) | Definitions for codebase-specific terms |
| [SECURITY.md](../SECURITY.md) | Secret hygiene & reporting posture |
| [HIVE_MIND.md](HIVE_MIND.md) | `hive_mind/` package (ConsensusEngine, HiveOrchestrator, DCP) |
| [BUG_BOT.md](BUG_BOT.md) | `core/bug_bot.py` workflow + `/bug` commands + Bugcrowd integration |
| [SHADOW_GOVERNANCE.md](SHADOW_GOVERNANCE.md) | Shadow governance, task mutation, retry wrapper |
| [CONTINUITY_VECTOR.md](CONTINUITY_VECTOR.md) | Five-axis baselines + three-axis runtime triad |
| [DEPLOYMENT.md](DEPLOYMENT.md) | Docker, Hugging Face Space, ports, routes |

---

## 14. Version note

Architecture details drift with commits; cross-check **`config.py`** and **`requirements.txt`** for ground truth when versions matter. Generated as a descriptive snapshot intended for outward sharing—adapt sections if your fork disables modules or adds new plugins.
