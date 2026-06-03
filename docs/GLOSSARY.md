# Glossary

Terms below are **project-local**: they explain how this codebase names things, not universal AI or neuroscience definitions.

---

## A–Z

### ChromaDB / semantic memory  
Vector store used for **retrieved** episodic memory and related passages. Persisted under your configured data root (often `chroma_db/` beside SQLite files). Distinct from per-turn chat logs in **`history.jsonl`**.

### Cognitive plugin  
A registered module in **`cognitive_architecture.py`** that can expose a **background `cycle_*` handler**, a **`prompt_formatter`** snippet, or both. Plugins compete for limited prompt space via **`PromptBudget`**.

### Comonadic Workspace Bridge  
Alternative state-regulation pipeline in **`core/context_engine.py`**, **`core/cognitive_ops.py`**, and **`core/cognitive_snapshot.py`**. Wraps the four-axis `CognitiveState` (`coherence`, `resonance`, `tension`, `shadow_depth`) and a structured `CognitivePayload` in an immutable `ContextWorker` so pipeline steps (`pedi_regulation_step`, `state_conditioned_llm`, etc.) compose by `extend` / `fork` / `merge` instead of mutating singletons. Used by the `--comonadic` chat flag and the standalone `interfaces/comonad_cli.py` demo. See [COMONADIC_BRIDGE.md](COMONADIC_BRIDGE.md).

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

### IIT / Φ (“phi”)  
**Integrated-information–inspired metrics** and qualia-axis bookkeeping in **`iit_consciousness.py`**. Computed proxies for introspection/diagnostics—not a clinical or physics claim.

### Identity Anchor (Center of Gravity)  
The resonance × coherence weighted mean of the last 20 non-quarantined, non-degenerate `IdentityBlock` entries in the **Svalbard ledger**, computed by **`PEDIEngine._get_identity_center_of_gravity`** in **`core/pedi_metrics.py`**. The **Regulation PEDI** pulls the active state toward this anchor each cycle when drift accumulates. Falls back to a deterministic `FALLBACK_ANCHOR` and a `HOLD_*` status when fewer than `MIN_USABLE_BLOCKS` (3) usable blocks exist.

### Lantern-4 Veto  
Post-generation gating step in **`GlobalWorkspace._lantern_4_veto`** that decides whether a turn deserves a sealed entry in the **Svalbard vault**. Requires resonance ≥ 0.85, semantic depth (length checks unless resonance ≥ 0.95), and flags the block as `quarantined=True` whenever `shadow_depth > 0.75`. Skipped entirely when the regulation PEDI reports `HOLD_*` or `CORRECTING`.

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

### PEDI — Continuity (`metrics/pedi.py`)  
**Performance & Efficiency Detection Index**. `PediIndex` measures state *fluidity* across context-window resets over a 7-need homeostasis vector. Records snapshots on every `assemble_prompt` call and raises `crisis_flag` when cumulative fluidity falls below `CRITICAL_FLUIDITY`. Telemetry in `data/pedi.db`. See [DMU_PEDI_TEST_PLAN.md](DMU_PEDI_TEST_PLAN.md).

### PEDI — Regulation (`core/pedi_metrics.py`)  
**Persistence-Embodiment-Drift Index**. `PEDIEngine` reads the last 20 Svalbard blocks to compute an **identity anchor**, then nudges the live `coherence` / `resonance` / `tension` state toward it. Emits `STABLE`, `CORRECTING`, `EVOLVING`, or `HOLD_<REASON>` per cycle. `shadow_depth` is tracked alongside but intentionally excluded from anchor-distance math. Powers the Fly-By-Wire path in `GlobalWorkspace.execute_cli_cycle`. See [VAULT_STABILITY_NOTES.md](VAULT_STABILITY_NOTES.md).

### **`PromptBudget`**  
Caps prompt growth by tier (core / cognitive / analysis / context) toward **`INFJ_MAX_TOTAL_PROMPT_CHARS`**.

### Shadow (`shadow.py`)  
Structured **prompt-time excerpts** from **`shadow.db`**, bounded by env caps (**`INFJ_SHADOW_PROMPT_*`**). Jung-influenced metaphor; **not** diagnosis.

### Svalbard Vault  
Tamper-evident JSONL ledger in **`core/svalbard_vault.py`**. Sealed `IdentityBlock` entries form a SHA-256 hash chain with optional HMAC signature (`DRIFT_VAULT_SECRET`); the **Lantern-4 Veto** decides which turns get sealed. Path is overridable via `DRIFT_VAULT_PATH` (default lives under `DATA_ROOT`). Backbone of the **Regulation PEDI**'s identity anchor.

### **SQLite “state brains”**  
Many subsystems (**being**, **embodiment**, **homeostasis**, **shadow**, etc.) persist orthogonal state as **`.db`** files under **`INFJ_DATA_DIR`** or **`PROJECT_ROOT`**.

---

## Related

- Mechanics and flow: [HOW_INFJ_BOT_WORKS.md](HOW_INFJ_BOT_WORKS.md)  
- Terms for credentials and scope: [SECURITY.md](../SECURITY.md)  
