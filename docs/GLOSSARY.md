# Glossary

Terms below are **project-local**: they explain how this codebase names things, not universal AI or neuroscience definitions.

---

## A–Z

### ChromaDB / semantic memory  
Vector store used for **retrieved** episodic memory and related passages. Persisted under your configured data root (often `chroma_db/` beside SQLite files). Distinct from per-turn chat logs in **`history.jsonl`**.

### Cognitive plugin  
A registered module in **`cognitive_architecture.py`** that can expose a **background `cycle_*` handler**, a **`prompt_formatter`** snippet, or both. Plugins compete for limited prompt space via **`PromptBudget`**.

### Critic (`INFJ_CRITIC_MODEL`)  
Optional second model pass that reviews the draft reply for grounding and persona rails before sending to the user (when wired in **`brain.py`**).

### CycleContext  
Object passed into plugin cycle handlers: includes **being**, **memory**, **brain**, orchestration clocks, and the last-interaction envelope. See **`cognitive_architecture.CycleContext`**.

### Distributed Response & Integrated Functional Thought (DRIFT)  
Marketing / architecture name for the **unified** stack described in the root README: companion interface, cognition modules, coordination hooks, persistent memory, and tools.

### Drift (**mode**)  
A **`/mode`** option with specific **guardrail scope** (`guardrails.mode_scope_rail`) plus optional **Drift-named memory seeds** surfaced when **`should_include_drift_context`** fires. Not a separate binary.

### **`drift.py`**  
Deterministic helpers: posture brief text and **targeted retrieval** queries for seeded Drift concepts. Does not pull code from external private repos.

### Global Workspace (`global_workspace.py`)  
Baars-inspired **spotlight**: limited simultaneous “conscious” entries; modules submit snippets with salience. Persisted via **`workspace.db`** when using the default data layout.

### Homeostasis (module)  
Regulates simulated **needs** over time (**`homeostasis.py`** + SQLite). Influences prompts and dashboards; informal metaphor, not a medical model.

### **`INFJ_DATA_DIR`**  
If set, relocates durable state (Chroma, SQLite DBs, `history.jsonl`, audits, etc.). Code stays in **`PROJECT_ROOT`**. Keeps clones portable and avoids stuffing the repo with runtime data.

### IIT / Φ (“phi”) / PhiProxy
**Integrated-information–inspired metrics** and qualia-axis bookkeeping in **`core/phi_proxy.py`** (renamed from `iit_consciousness.py`). Computed proxies for introspection/diagnostics—not a clinical or physics claim. Surfaces as `Φ Ω` on the Observatory dashboard. See [WEB_INTERFACE.md](WEB_INTERFACE.md).

### Continuity Vector (three-axis triad)
The live `[memory, state, novelty]` 3-bit telemetry computed every cycle by **`core/continuity_vector.py`**. Each axis is a threshold over `CognitiveContext` (retrieved notes/history depth, coherence/variance, shadow influence/new entities). The 8 patterns get named labels (COMPANION, REGULATED, EXPLORER, TASK, RESONANT, FRONTIER, FULL COUNCIL, QUIET). Distinct from the five-axis ablation continuity vector that also lives in the same file. See [SUBSYSTEMS.md](SUBSYSTEMS.md#5-continuity-vector--memory--state--novelty-triad).

### Distributed Cognition Protocol (DCP)
Lightweight in-process message format under **`hive_mind/protocol/dcp.py`**: `DCPMessage`, `NodeRole` (`PRIMARY|CRITIC|BACKUP|OBSERVER`), and `Resolution` (`ADOPTED|TABLED|REJECTED|PENDING`). The substrate for the Hive Mind’s propose/vote/resolve loop.

### Hive Mind / Consensus Engine
The package at **`hive_mind/`** with `HiveOrchestrator` (node registry + status), `ConsensusEngine` (in-memory propose → vote → resolve threads), and the DCP message types. Exposed live via FastAPI `/api/hive` and `/api/health`. The longer-term plan lives in [HIVE_ROADMAP.md](HIVE_ROADMAP.md).

### **`InfjBrain`**  
Primary LLM wrapper in **`brain.py`**: Gemini (and optional Ollama fallback), streaming, tooling hooks where enabled.

### **`InfjMemory`**  
Chroma-backed memory in **`memory.py`**: save interactions after **secret scrubbing**, hybrid search/top‑k, optional document sidecar integrations.

### **“Jude” / user-facing name**  
Default narrative name for the human in prompts and seeded content. Replace in your fork if needed.

### **Layer 1–5**  
Architectural shorthand in the README: **Interface**, **Cognition**, **Coordination**, **Memory**, **Tools & Safety**. Layers overlap in code—it is an organizational map, not a strict dependency DAG.

### **Ollama**  
Local inference path via **`OllamaBridge`** in **`local_llm.py`** when **`INFJ_USE_LOCAL_FALLBACK`** is enabled.

### **`PromptBudget`**  
Caps prompt growth by tier (core / cognitive / analysis / context) toward **`INFJ_MAX_TOTAL_PROMPT_CHARS`**.

### Shadow (`shadow.py`)  
Structured **prompt-time excerpts** from **`shadow.db`**, bounded by env caps (**`INFJ_SHADOW_PROMPT_*`**). Jung-influenced metaphor; **not** diagnosis.

### Shadow governance (`shadow_governance.py`)
Mode-aware control layer **on top of** `shadow.py`: enforces TTL exponential decay, a per-mode accumulation cap, and a promotion threshold gated on `consistency_window`. The active mode (`SECURITY`/`BALANCED`/`CONSERVATIVE`) is derived from the current DRIFT chat mode via `resolve_mode()`. Output is a single `shadow_influence ∈ [0, MAX]` that Nexus uses to **penalize** confidence (never veto). See [SUBSYSTEMS.md § 1](SUBSYSTEMS.md#1-shadow-governance--coreshadow_governancepy).

### Task mutator (`task_mutator.py`)
Auto-evolve layer for DriftSurface tasks. When shadow influence exceeds the promotion threshold and `intent_stability < 0.6`, runs a mode-dependent mutation: `SECURITY` archives, `BALANCED` rewrites the task as a reflection note, `CONSERVATIVE` marks it `GHOST` with an insight flag. Forgiveness restores `GHOST` tasks to `OPEN` once shadow decays. See [SUBSYSTEMS.md § 2](SUBSYSTEMS.md#2-task-mutator--coretask_mutatorpy).

### Retry wrapper (`retry_wrapper.py`)
Dynamic-timeout + exponential-backoff wrapper around LLM generation calls. Computes `max(60, 20 + 25 × ⌊prompt_length / 1000⌋)` seconds in standard mode and a fixed `150s/300tok/T=0.3` profile in ablation mode. Only retries `TimeoutError`; everything else fails fast. Sets `DRIFT_LOCAL_TIMEOUT` for downstream runners. See [SUBSYSTEMS.md § 3](SUBSYSTEMS.md#3-retry-wrapper--coreretry_wrapperpy).

### **SQLite “state brains”**  
Many subsystems (**being**, **embodiment**, **homeostasis**, **shadow**, etc.) persist orthogonal state as **`.db`** files under **`INFJ_DATA_DIR`** or **`PROJECT_ROOT`**.

---

## Related

- Mechanics and flow: [HOW_INFJ_BOT_WORKS.md](HOW_INFJ_BOT_WORKS.md)  
- Subsystem deep dives: [SUBSYSTEMS.md](SUBSYSTEMS.md)  
- Web interface and Observatory: [WEB_INTERFACE.md](WEB_INTERFACE.md)  
- Terms for credentials and scope: [SECURITY.md](../SECURITY.md)  
