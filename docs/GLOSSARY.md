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

### IdentityBlock / EmotionalAnchor  
The two dataclasses serialized into the **Svalbard ledger** (`core/svalbard_vault.py`). An `IdentityBlock` is one append-only entry — `timestamp`, `event_summary`, `user_quote`, `system_quote`, an `EmotionalAnchor` (`coherence`, `tension`, `resonance`, `shadow_depth`), `prior_hash`, `quarantined`, `block_hash`. See [IDENTITY_VAULT.md](IDENTITY_VAULT.md).

### Identity gravity center  
The resonance×coherence-weighted average of the four emotional axes across the last ~20 non-quarantined Svalbard blocks. **PEDI Engine** (`core/pedi_metrics.py`) uses this as the anchor it pulls the perceived state toward.

### **“Jude” / user-facing name**  
Default narrative name for the human in prompts and seeded content. Replace in your fork if needed.

### Lantern-4 veto  
The post-response gate inside **`GlobalWorkspace`** that decides whether a turn deserves to be sealed into the Svalbard ledger. Requires high `resonance` and enough semantic density; high `shadow_depth` triggers the `quarantined=True` flag so the block is preserved but ignored by PEDI's gravity-center math. See [IDENTITY_VAULT.md § 4](IDENTITY_VAULT.md#4-wiring-in-globalworkspace).

### **Layer 1–5**  
Architectural shorthand in the README: **Interface**, **Cognition**, **Coordination**, **Memory**, **Tools & Safety**. Layers overlap in code—it is an organizational map, not a strict dependency DAG.

### **Ollama**  
Local inference path via **`OllamaBridge`** in **`local_llm.py`** when **`INFJ_USE_LOCAL_FALLBACK`** is enabled.

### PEDI (two distinct modules — **disambiguation**)  
The acronym is reused for two unrelated subsystems. Always disambiguate when discussing them:

- **`metrics/pedi.py` — Performance and Efficiency Detection Index.** Tracks fluidity of the 7-dimensional **homeostatic** state vector (`energy`, `coherence`, `integration`, `connection`, `growth`, `autonomy`, `integrity`) across context-window resets. SQLite-backed (`pedi.db`). See [DMU_PEDI_TEST_PLAN.md](DMU_PEDI_TEST_PLAN.md).
- **`core/pedi_metrics.py` — Persistence–Embodiment–Drift Index (PEDIEngine).** Fly-by-wire identity regulator that smooths the 4-dimensional **emotional** state (`coherence`, `tension`, `resonance`, `shadow_depth`) toward the **identity gravity center** of recent Svalbard blocks. In-memory accumulator. See [IDENTITY_VAULT.md](IDENTITY_VAULT.md).

### **`PromptBudget`**  
Caps prompt growth by tier (core / cognitive / analysis / context) toward **`INFJ_MAX_TOTAL_PROMPT_CHARS`**.

### `raw_user_input`  
Optional keyword argument on `DriftBrain.think / think_stream / agent_turn / agent_turn_stream`. When provided, the **security scanner** scans only the literal user message instead of the assembled prompt, eliminating false positives from system-prompt content. If omitted, the scanner falls back to extracting whatever follows the last `\nUser: ` / `\nUser:\n` marker. See [SECURITY_DEFENSE.md § 3](SECURITY_DEFENSE.md#3-the-raw_user_input-separation-fix-in-44fd821).

### Security scanner (`SecurityScanner`, `SecurityScanResult`)  
Regex/heuristic input pre-filter in **`core/security_defense.py`**. Scores each turn against four categories (`prompt_injection`, `data_exfiltration`, `tool_misuse`, `memory_manipulation`), blocks at `>= 0.60` or any `AUTO_BLOCK_PATTERNS` hit, sanitizes at `>= 0.20`. Detections go to `security_audit.jsonl` at `PROJECT_ROOT`. See [SECURITY_DEFENSE.md](SECURITY_DEFENSE.md).

### Shadow (`shadow.py`)  
Structured **prompt-time excerpts** from **`shadow.db`**, bounded by env caps (**`INFJ_SHADOW_PROMPT_*`**). Jung-influenced metaphor; **not** diagnosis.

### Svalbard vault (`core/svalbard_vault.py`)  
Append-only, hash-chained, HMAC-signed JSONL ledger of high-resonance "core memories". Each line is an `IdentityBlock`; the latest `block_hash` is signed into `<VAULT_PATH>.sig` with **`DRIFT_VAULT_SECRET`**. Paths are controlled by **`DRIFT_VAULT_PATH`** (falls back to `<DATA_ROOT>/svalbard_ledger.jsonl`). See [IDENTITY_VAULT.md](IDENTITY_VAULT.md).

### **SQLite “state brains”**  
Many subsystems (**being**, **embodiment**, **homeostasis**, **shadow**, etc.) persist orthogonal state as **`.db`** files under **`INFJ_DATA_DIR`** or **`PROJECT_ROOT`**.

---

## Related

- Mechanics and flow: [HOW_INFJ_BOT_WORKS.md](HOW_INFJ_BOT_WORKS.md)  
- Terms for credentials and scope: [SECURITY.md](../SECURITY.md)  
