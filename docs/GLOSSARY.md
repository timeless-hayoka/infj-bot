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
**Integrated-information–inspired metrics** and qualia-axis bookkeeping in **`core/phi_proxy.py`** (formerly `iit_consciousness.py`). Computed proxies for introspection/diagnostics — not a clinical or physics claim. The current implementation also tracks **global-workspace capacity** alongside the integration measure.

### Council / Council of 7
Seven persistent inner voices (Vesper, Forge, Riven, Seraph, Soren, Sentinel, Eden) defined in **`core/hive/council_member.py`**. Each holds its own fractal memory subspace, energy budget, and win/loss tracking. The Council is consulted by **Elysium** during background reflection and on `/hive nexus decide` runs.

### Continuity Vector
Five-axis scoring of conversational continuity (identity, tone, narrative, memory, state) defined in **`core/continuity_vector.py`**. Pooled across baseline sessions to compute per-axis variance for the falsifiability-statement thresholds.

### DMU — Dynamic Memory Unit
Module **`memory/dmu.py`** that re-ranks vector-search candidates by a composite **Memory Persistence Score (MPS)**. Adds exponential time-decay (modulated by emotional weight) and a recency bonus on top of plain cosine similarity. Telemetry lives in `data/dmu.db`. See [DMU_PEDI_TEST_PLAN.md](DMU_PEDI_TEST_PLAN.md).

### Elysium / Nexus Loop
Decision engine in **`core/hive/elysium.py`** that runs the five-phase Nexus Loop (Ignition → Proposals → Critique → Integration → Resolution) over Council voices. Surfaced via `/hive nexus decide <goal>` and as a periodic background reflection.

### Experiment Control / Freeze Mode
Scaffold in **`core/experiment_control.py`** for ablation runs. Gates which subsystems are active on a per-run basis (`control.is_active("memory")`, `control.is_active("state")`, …). Used by `tests/ablation_runner.py` and `tests/collect_baseline.py` to enforce that mutation/self-modify/DMU changes are never combined.

### Logic Chain (`logic_chain.py`)
Reasoning-trace memory in **`core/logic_chain.py`**: groups attempted approaches by a query fingerprint so the LLM is shown what has already been tried. Persists chains via `DriftMemory` so they survive restarts. See [SECURITY_AND_LOGIC_CHAIN.md](SECURITY_AND_LOGIC_CHAIN.md).

### MPS — Memory Persistence Score
Composite score in `[0, 1]` produced by the **DMU**: `MPS = w_sim·S + w_time·R(t,E) + w_emo·E + w_rec·recency`. Weights live in `MPS_WEIGHTS` (relocatable to config).

### PEDI — Performance & Efficiency Detection Index
Module **`metrics/pedi.py`** that measures **state fluidity** across context-window resets. Computes the Euclidean jump between pre- and post-reset homeostatic state vectors and converts it to a 0–1 fluidity score; long stretches of low fluidity raise a crisis flag. Telemetry in `data/pedi.db`.

### Run Logger
Thread-safe SQLite logger in **`core/run_logger.py`** used by the upgrade infrastructure to record `run_id`, `git_hash`, config snapshot, state events, memory selection events, and continuity metrics for every session. Inspect with `python tests/inspect_logs.py`.

### Security Scanner / Security Defense Layer
Pre-generation regex scanner in **`core/security_defense.py`** that classifies user input into `prompt_injection`, `data_exfiltration`, `tool_misuse`, or `memory_manipulation`. Auto-blocks critical patterns, sanitizes warn-tier inputs, and appends every detection to `security_audit.jsonl`. See [SECURITY_AND_LOGIC_CHAIN.md](SECURITY_AND_LOGIC_CHAIN.md).

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

### **SQLite “state brains”**  
Many subsystems (**being**, **embodiment**, **homeostasis**, **shadow**, etc.) persist orthogonal state as **`.db`** files under **`INFJ_DATA_DIR`** or **`PROJECT_ROOT`**.

---

## Related

- Mechanics and flow: [HOW_INFJ_BOT_WORKS.md](HOW_INFJ_BOT_WORKS.md)  
- Terms for credentials and scope: [SECURITY.md](../SECURITY.md)  
