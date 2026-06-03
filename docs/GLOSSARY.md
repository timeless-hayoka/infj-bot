# Glossary

Terms below are **project-local**: they explain how this codebase names things, not universal AI or neuroscience definitions.

---

## A–Z

### AnchorResult
Return type of `PEDIEngine._get_identity_center_of_gravity()` in **`core/pedi_metrics.py`**. Carries `(anchor, valid, reason)`. When `valid=False`, callers must treat the cycle as **HOLD** and skip ledger writes. See [IDENTITY_REGULATOR.md](IDENTITY_REGULATOR.md).

### ChromaDB / semantic memory
Vector store used for **retrieved** episodic memory and related passages. Persisted under your configured data root (often `chroma_db/` beside SQLite files). Distinct from per-turn chat logs in **`history.jsonl`**.

### CognitivePayload
Pydantic value carried through the **Comonadic Workspace Bridge**. Fields: `user_input`, `internal_log` (PEDI dampening notes), `response` (Affective Logic Gate posture), `metadata`. Lives in **`core/context_engine.py`**.

### CognitiveState
Pydantic state inside the **Comonadic Workspace Bridge**: `coherence`, `resonance`, `tension`, `shadow_depth`, all clamped to `[0, 1]`. The first three are the dimensions used by **PEDI** for anchor distance.

### Comonadic Workspace Bridge
Opt-in cognitive pipeline (`--comonadic` flag on `interfaces/main.py`) that runs a turn as a chain of pure operations over `(CognitiveState, CognitivePayload)`. See [COMONADIC_BRIDGE.md](COMONADIC_BRIDGE.md). Code in **`core/context_engine.py`**, **`core/cognitive_ops.py`**, **`core/cognitive_snapshot.py`**, **`interfaces/comonad_cli.py`**.

### ContextWorker
Comonad wrapper around a `Context[A]`. Exposes `current()`, `state`, read-only `history`, and the `extend(op)` / `fork(ops)` / `merge(branches, selector)` operations.

### Cognitive plugin  
A registered module in **`cognitive_architecture.py`** that can expose a **background `cycle_*` handler**, a **`prompt_formatter`** snippet, or both. Plugins compete for limited prompt space via **`PromptBudget`**.

### Critic (`INFJ_CRITIC_MODEL`)  
Optional second model pass that reviews the draft reply for grounding and persona rails before sending to the user (when wired in **`brain.py`**).

### CycleContext  
Object passed into plugin cycle handlers: includes **being**, **memory**, **brain**, orchestration clocks, and the last-interaction envelope. See **`cognitive_architecture.CycleContext`**.

### Distributed Response & Integrated Functional Thought (DRIFT)
Marketing / architecture name for the **unified** stack described in the root README: companion interface, cognition modules, coordination hooks, persistent memory, and tools.

### DMU (Dynamic Memory Unit)
Re-ranks retrieved memories by a composite **Memory Persistence Score** that combines semantic similarity, emotionally-dampened exponential decay, raw emotion weight, and a recency bonus. Two implementations exist: **`memory/dmu.py`** (engine) and **`core/dmu_scoring.py`** (the production additive **MPS** scorer used in the orchestrator).

### Drift (**mode**)  
A **`/mode`** option with specific **guardrail scope** (`guardrails.mode_scope_rail`) plus optional **Drift-named memory seeds** surfaced when **`should_include_drift_context`** fires. Not a separate binary.

### **`drift.py`**
Deterministic helpers: posture brief text and **targeted retrieval** queries for seeded Drift concepts. Does not pull code from external private repos.

### Fly-By-Wire
Shorthand for the regulation step in `GlobalWorkspace.execute_cli_cycle`: the raw active state is regulated by **PEDI** *before* the LLM is queried, so generation runs against a stabilised cognitive state. Status lines like `[*] PEDI Fly-By-Wire status: CORRECTING` are emitted by the CLI when the regulator intervenes. See [IDENTITY_REGULATOR.md](IDENTITY_REGULATOR.md).

### Global Workspace (`global_workspace.py`)
Baars-inspired **spotlight**: limited simultaneous "conscious" entries; modules submit snippets with salience. Persisted via **`workspace.db`** when using the default data layout. Also owns the **Fly-By-Wire** PEDI cycle and the **Lantern-4** veto.

### HOLD_* (PEDI statuses)
Family of statuses returned by `PEDIEngine.evaluate_cycle` when the ledger cannot be trusted this turn: `HOLD_NO_VAULT`, `HOLD_NO_BLOCKS`, `HOLD_COLD_START`, `HOLD_READ_ERROR`. Callers must not seal new ledger blocks while in any HOLD state.

### Identity Block
Tamper-evident record sealed to the Svalbard ledger. SHA-256 hash-chained to its predecessor and signed via HMAC keyed by `DRIFT_VAULT_SECRET`.

### Homeostasis (module)  
Regulates simulated **needs** over time (**`homeostasis.py`** + SQLite). Influences prompts and dashboards; informal metaphor, not a medical model.

### **`INFJ_DATA_DIR`**  
If set, relocates durable state (Chroma, SQLite DBs, `history.jsonl`, audits, etc.). Code stays in **`PROJECT_ROOT`**. Keeps clones portable and avoids stuffing the repo with runtime data.

### IIT / Φ (“phi”)  
**Integrated-information–inspired metrics** and qualia-axis bookkeeping in **`iit_consciousness.py`**. Computed proxies for introspection/diagnostics—not a clinical or physics claim.

### **`InfjBrain`**  
Primary LLM wrapper in **`brain.py`**: Gemini (and optional Ollama fallback), streaming, tooling hooks where enabled.

### **`InfjMemory`**  
Chroma-backed memory in **`memory.py`**: save interactions after **secret scrubbing**, hybrid search/top‑k, optional document sidecar integrations.

### **"Jude" / user-facing name**
Default narrative name for the human in prompts and seeded content. Replace in your fork if needed.

### Lantern-4 veto
Last gate before a turn is sealed to the Svalbard ledger. Checks resonance ≥ 0.85, semantic depth (`5+` user words, `10+` system words unless resonance ≥ 0.95), and marks blocks as **quarantined** when `shadow_depth > 0.75`. Implementation: `GlobalWorkspace._lantern_4_veto`. See [IDENTITY_REGULATOR.md](IDENTITY_REGULATOR.md).

### **Layer 1–5**
Architectural shorthand in the README: **Interface**, **Cognition**, **Coordination**, **Memory**, **Tools & Safety**. Layers overlap in code—it is an organizational map, not a strict dependency DAG.

### MPS (Memory Persistence / Prioritization Score)
Composite score in `[0, 1]` returned by `core/dmu_scoring.py.compute_mps`. Used to re-rank ChromaDB candidates before they enter the prompt. Weights live in `MPS_WEIGHTS`; tune from config rather than editing the module.

### **Ollama**
Local inference path via **`OllamaBridge`** in **`local_llm.py`** when **`INFJ_USE_LOCAL_FALLBACK`** is enabled.

### PEDI (Persistence-Embodiment-Drift Index)
`PEDIEngine` in **`core/pedi_metrics.py`** — the production identity regulator. Pulls a weighted anchor from the last 20 Svalbard blocks (3 dims: coherence, resonance, tension) and returns `STABLE / CORRECTING / EVOLVING / HOLD_*` per cycle. See [IDENTITY_REGULATOR.md](IDENTITY_REGULATOR.md). Not to be confused with `PediIndex` in `metrics/pedi.py`, which measures **state fluidity** instead — see [DMU_PEDI_TEST_PLAN.md](DMU_PEDI_TEST_PLAN.md).

### **`PromptBudget`**
Caps prompt growth by tier (core / cognitive / analysis / context) toward **`INFJ_MAX_TOTAL_PROMPT_CHARS`**.

### Shadow (`shadow.py`)
Structured **prompt-time excerpts** from **`shadow.db`**, bounded by env caps (**`INFJ_SHADOW_PROMPT_*`**). Jung-influenced metaphor; **not** diagnosis.

### **SQLite "state brains"**
Many subsystems (**being**, **embodiment**, **homeostasis**, **shadow**, etc.) persist orthogonal state as **`.db`** files under **`INFJ_DATA_DIR`** or **`PROJECT_ROOT`**.

### Svalbard Vault
Tamper-evident JSONL ledger at `<DATA_ROOT>/svalbard_ledger.jsonl` (override with `DRIFT_VAULT_PATH`). Each accepted exchange becomes an `IdentityBlock` chained to its predecessor by SHA-256 and signed with HMAC using `DRIFT_VAULT_SECRET`. The **PEDI** anchor is computed from the last 20 blocks. See `core/svalbard_vault.py`.

### TransitionComparator
Diagnostic in `core/cognitive_snapshot.py` that scores how well a predictor function reproduces a real `CognitiveState` transition. `accuracy_score = max(0, 1 − Σ|delta_error| / 4)`.

---

## Related

- Mechanics and flow: [HOW_INFJ_BOT_WORKS.md](HOW_INFJ_BOT_WORKS.md)  
- Terms for credentials and scope: [SECURITY.md](../SECURITY.md)  
