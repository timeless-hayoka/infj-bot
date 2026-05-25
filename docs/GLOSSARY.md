# Glossary

Terms below are **project-local**: they describe how the PHI // DRIFT codebase names things, not universal AI or neuroscience definitions.

Environment variables generally have a `DRIFT_*` form; legacy `INFJ_*` names are still read for back-compatibility (see `core/config.py`).

---

## A–Z

### Ablation suite
6-condition test harness (`tests/ablation_suite.py`) that disables or stubs one cognitive subsystem at a time and measures the impact on prompt length, latency, and response shape. See the **What's New** section of the root [README](../README.md) for the latest live run.

### ChromaDB / semantic memory
Vector store used for **retrieved** episodic memory and concept passages. Persisted under your configured data root. Distinct from per-turn chat logs in `history.jsonl`.

### Cognitive plugin
A registered module in `core/cognitive_architecture.py` that exposes a background `cycle_handler`, a `prompt_formatter` snippet, or both. Plugins compete for limited prompt space via `PromptBudget`.

### Continuity Vector
Five-axis behavioral-continuity measurement (`core/continuity_vector.py`): `entity_overlap`, `goal_overlap`, `tone_similarity`, `memory_reference_rate`, `state_influence`. Drives the falsifiability test in [FALSIFIABILITY.md](FALSIFIABILITY.md).

### Critic (`DRIFT_CRITIC_MODEL`)
Optional second-model pass that reviews the draft reply for grounding and persona rails before sending to the user (wired in `core/brain.py`).

### CycleContext
Object passed into plugin cycle handlers: includes **being**, **memory**, **brain**, orchestration clocks, and the last-interaction envelope. See `core/cognitive_architecture.CycleContext`.

### DMU / MPS (Memory Prioritization Score)
Additive re-ranking score in `core/dmu_scoring.py` applied after the wide ChromaDB pull. Six weighted factors: `decay`, `reinf`, `contextual`, `recency_bias`, `novelty`, `state_align`. The Condition D ablation removes this re-ranker and is the only condition that produced a measurable prompt-length delta in the May 2026 live run.

### Distributed Response & Integrated Functional Thought (DRIFT)
Architecture name for the unified stack described in the root README: companion interface, cognition modules, coordination hooks, persistent memory, and tools.

### Drift (**mode**)
A `/mode` option with specific guardrail scope (`core/guardrails.mode_scope_rail`) plus a freeform-exploration posture. Modes are listed in `core/commands.MODES`.

### Experiment Control
`core/experiment_control.ExperimentControl` manages freeze flags (memory, state, self-modify, mutation, novelty), validates config consistency, and records run lifecycle events. Used by the ablation suite to enforce discipline.

### Global Workspace (`core/global_workspace.py`)
Baars-inspired spotlight: limited simultaneous "conscious" entries; modules submit snippets with salience. Persisted via `workspace.db`.

### Homeostasis (module)
Regulates simulated **needs** over time (`core/homeostasis.py` + SQLite). Influences prompts and dashboards; informal metaphor, not a medical model.

### `INFJ_DATA_DIR` / `DRIFT_DATA_DIR`
If set, relocates durable state (Chroma, SQLite DBs, `history.jsonl`, audits, etc.) away from the project root, keeping clones portable. See `config_adapter.py` for the resolution order.

### `DriftBrain`
Primary LLM wrapper in `core/brain.py`: handles Gemini (new `google.genai` SDK with legacy fallback), optional Groq, optional Kimi, optional Ollama fallback, streaming, and tool execution.

### `DriftMemory`
Chroma-backed memory in `core/memory.py`: save interactions after **secret scrubbing**, hybrid search/top-k, optional document sidecar integrations.

### Logic Chain (`core/logic_chain.py`)
Reasoning-trace memory. A `LogicChain` records `ChainNode` steps (approach, result, status) per query fingerprint. `ChainNavigator` finds or creates chains, persists them through `DriftMemory`, and injects a `[REASONING CHAIN]` block into prompts so the model does not retry failed approaches.

### "Jude" / user-facing name
Default narrative name for the human in seeded prompts and concepts. Replace in your fork if needed.

### **Layer map**
Architectural shorthand in the README: **Interface**, **Orchestration**, **Cognition**, **Memory**, **Safety**. Layers overlap in code — it is an organizational map, not a strict dependency DAG.

### Ollama
Local inference path via `OllamaBridge` in `core/local_llm.py` when `DRIFT_USE_LOCAL_FALLBACK` is enabled. Default model is `qwen3:4b`.

### PHI Council of Seven
Seven named roles mapped to internal modules in `core/phi_council.COUNCIL_MAPPING`: **Aura** (emotional field), **Logic** (cognition), **Meme** (metacognition), **Vibe** (intuition), **Ethos** (values), **Pulse** (homeostasis), **Nexus** (coordination). The council deliberates in the background; it does not gate the read path.

### Phi Proxy (formerly "IIT consciousness")
`core/phi_proxy.py` — an **IIT-inspired functional analog**, not a literal implementation of Integrated Information Theory. Computes a 7-axis qualia state (`valence`, `arousal`, `complexity`, `unity`, `boundaries`, `depth`, `luminosity`) plus a Φ proxy from active mechanisms and workspace integration. Persisted in `phi_proxy.db`.

### `PromptBudget`
Caps prompt growth by tier (core / cognitive / analysis / context) toward `INFJ_MAX_TOTAL_PROMPT_CHARS` (default 12 000).

### Security Scanner (`core/security_defense.py`)
Pre-LLM scanner across four attack categories: **prompt injection**, **data exfiltration**, **tool misuse**, **memory manipulation**. Auto-blocks high-confidence patterns and warn-sanitizes medium-confidence ones. Writes a JSONL audit log to `security_audit.jsonl`. Invoked at API, CLI, and brain boundaries.

### Shadow (`core/shadow.py`)
Structured prompt-time excerpts from `shadow.db`, bounded by env caps (`INFJ_SHADOW_PROMPT_*`). Jung-influenced metaphor; not diagnosis.

### SQLite "state brains"
Many subsystems (being, embodiment, homeostasis, shadow, phi_proxy, etc.) persist orthogonal state as `.db` files under the configured data dir.

### Strong Continuous Mode
Background `consciousness_loop` that fires every `BACKGROUND_CYCLE_SECONDS` (default 20s) so being, shadow, and homeostasis evolve even when the user is silent. Toggled by `STRONG_CONTINUOUS_MODE`.

---

## Related

- Chat-turn flow: [HOW_INFJ_BOT_WORKS.md](HOW_INFJ_BOT_WORKS.md)
- Newer subsystem reference: [SUBSYSTEMS.md](SUBSYSTEMS.md)
- Credentials and scope: [../SECURITY.md](../SECURITY.md)
