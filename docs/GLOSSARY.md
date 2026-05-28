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

### IIT / Φ (“phi”)  
**Integrated-information–inspired metrics** and qualia-axis bookkeeping in **`iit_consciousness.py`**. Computed proxies for introspection/diagnostics—not a clinical or physics claim.

### **`InfjBrain`**  
Primary LLM wrapper in **`brain.py`**: Gemini (and optional Ollama fallback), streaming, tooling hooks where enabled.

### **`InfjMemory`**  
Chroma-backed memory in **`memory.py`**: save interactions after **secret scrubbing**, hybrid search/top‑k, optional document sidecar integrations.

### Identity Block  
Single record in the **Svalbard Vault** ledger. Carries an `EmotionalAnchor` (coherence/tension/resonance/shadow_depth), the user and system quotes, a SHA-256 `block_hash`, and the `prior_hash` of the previous block. Identical to the dataclass `IdentityBlock` in **`svalbard_vault.py`**.

### **“Jude” / user-facing name**  
Default narrative name for the human in prompts and seeded content. Replace in your fork if needed.

### Lantern-4 veto  
Gate in **`global_workspace.GlobalWorkspace._lantern_4_veto`** that decides whether a turn can be sealed into the Svalbard Vault. Requires `resonance ≥ 0.85` and (unless resonance ≥ 0.95) minimum semantic density. When `shadow_depth > 0.75` the block is admitted but marked **quarantined**.

### **Layer 1–5**  
Architectural shorthand in the README: **Interface**, **Cognition**, **Coordination**, **Memory**, **Tools & Safety**. Layers overlap in code—it is an organizational map, not a strict dependency DAG.

### **Ollama**  
Local inference path via **`OllamaBridge`** in **`local_llm.py`** when **`INFJ_USE_LOCAL_FALLBACK`** is enabled.

### PEDI / Persistence-Embodiment-Drift Index  
Closed-loop regulator over the four-axis emotional state (`coherence`, `resonance`, `tension`, `shadow_depth`) implemented in **`pedi_metrics.py`**. Each cycle it computes a center of gravity from the vault's recent un-quarantined blocks, blends the active state toward it, and reports a status of `NO_ANCHOR`, `EVOLVING`, `CORRECTING`, or `STABLE`. See [IDENTITY_REGULATOR.md](IDENTITY_REGULATOR.md).

### **`PromptBudget`**  
Caps prompt growth by tier (core / cognitive / analysis / context) toward **`INFJ_MAX_TOTAL_PROMPT_CHARS`**.

### Quarantined memory  
An `IdentityBlock` written with `quarantined=True`. Still hashed and chained for tamper-evidence, but **excluded** from PEDI's center-of-gravity computation so a destabilizing peak (e.g. high shadow depth) cannot pull the regulator off-axis.

### `raw_user_input` (security isolation)  
Optional argument added to `DriftBrain.think`, `think_stream`, `agent_turn`, and `agent_turn_stream` in **May 2026**. Lets the interface layer pass the **original** user message alongside the **assembled** prompt so the security scanner only inspects the human-authored text and ignores trusted internal scaffolding. See [HOW_INFJ_BOT_WORKS.md § Security input isolation](HOW_INFJ_BOT_WORKS.md#71-security-input-isolation-may-2026).

### Shadow (`shadow.py`)  
Structured **prompt-time excerpts** from **`shadow.db`**, bounded by env caps (**`INFJ_SHADOW_PROMPT_*`**). Jung-influenced metaphor; **not** diagnosis.

### **SQLite “state brains”**  
Many subsystems (**being**, **embodiment**, **homeostasis**, **shadow**, etc.) persist orthogonal state as **`.db`** files under **`INFJ_DATA_DIR`** or **`PROJECT_ROOT`**.

### Svalbard Vault  
Append-only, hash-chained, HMAC-signed JSONL ledger of milestone exchanges. Lives at `DRIFT_VAULT_PATH` (or `${INFJ_DATA_DIR}/svalbard_ledger.jsonl`); signed by `DRIFT_VAULT_SECRET`. Implementation in **`svalbard_vault.py`**; full reference in [IDENTITY_REGULATOR.md](IDENTITY_REGULATOR.md).

---

## Related

- Mechanics and flow: [HOW_INFJ_BOT_WORKS.md](HOW_INFJ_BOT_WORKS.md)  
- Identity persistence & regulation: [IDENTITY_REGULATOR.md](IDENTITY_REGULATOR.md)  
- Terms for credentials and scope: [SECURITY.md](../SECURITY.md)  
