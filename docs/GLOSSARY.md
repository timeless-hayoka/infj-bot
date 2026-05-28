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

### **IdentityBlock**  
A single sealed entry in the **Svalbard Vault** ledger. Carries `timestamp`, `event_summary`, the user/system quotes, an `EmotionalAnchor` (coherence / tension / resonance / shadow_depth), a `prior_hash`, an optional `quarantined` flag, and its own SHA-256 `block_hash`. Hashes chain block-to-block; the latest hash is HMAC-signed via **`DRIFT_VAULT_SECRET`**. See **`core/svalbard_vault.py`**.

### **Lantern-4 Veto**  
Post-action gate in **`GlobalWorkspace.execute_cli_cycle`** that decides whether an exchange is worth sealing into the **Svalbard Vault**. Requires resonance ≥ 0.85, a minimum semantic density unless resonance ≥ 0.95, and quarantines blocks where `shadow_depth > 0.75` so they enter the ledger but do not anchor **PEDI**.

### **“Jude” / user-facing name**  
Default narrative name for the human in prompts and seeded content. Replace in your fork if needed.

### **Layer 1–5**  
Architectural shorthand in the README: **Interface**, **Cognition**, **Coordination**, **Memory**, **Tools & Safety**. Layers overlap in code—it is an organizational map, not a strict dependency DAG.

### **Ollama**  
Local inference path via **`OllamaBridge`** in **`local_llm.py`** when **`INFJ_USE_LOCAL_FALLBACK`** is enabled.

### **PEDI** (Persistence-Embodiment-Drift Index)  
Identity regulator in **`core/pedi_metrics.py`**. Reads the last ~20 vault blocks as an emotional "center of gravity" and adjusts the active state before generation. Emits one of `STABLE` / `CORRECTING` / `EVOLVING` per cycle, with `NO_ANCHOR` when the vault is empty. **Note:** distinct from the metrics-layer index at **`metrics/pedi.py`** (Performance & Efficiency Detection Index) used by **`DMU_PEDI_TEST_PLAN.md`** — same acronym, different layer.

### **`PromptBudget`**  
Caps prompt growth by tier (core / cognitive / analysis / context) toward **`INFJ_MAX_TOTAL_PROMPT_CHARS`**.

### **SecurityScanner** (`core/security_defense.py`)  
First-stage input defense. Pure regex + heuristic scoring across four categories (prompt injection, data exfiltration, tool misuse, memory manipulation). Blocks at `overall_score ≥ 0.60` or on any auto-block pattern; warns and sanitizes at `≥ 0.20`. Operated via **`/security status | audit | test`**. See [SECURITY_SCANNER.md](SECURITY_SCANNER.md).

### Shadow (`shadow.py`)  
Structured **prompt-time excerpts** from **`shadow.db`**, bounded by env caps (**`INFJ_SHADOW_PROMPT_*`**). Jung-influenced metaphor; **not** diagnosis.

### **SQLite “state brains”**  
Many subsystems (**being**, **embodiment**, **homeostasis**, **shadow**, etc.) persist orthogonal state as **`.db`** files under **`INFJ_DATA_DIR`** or **`PROJECT_ROOT`**.

### **Svalbard Vault** (`core/svalbard_vault.py`)  
Tamper-evident JSONL identity ledger. Each significant exchange is sealed as an **IdentityBlock** in a SHA-256 hash chain, with the latest hash HMAC-signed using **`DRIFT_VAULT_SECRET`**. Acts as DRIFT's long-term episodic identity memory and as the anchor source for **PEDI**. Path defaults to **`INFJ_DATA_DIR`** + `svalbard_ledger.jsonl`; override with **`DRIFT_VAULT_PATH`**.

---

## Related

- Mechanics and flow: [HOW_INFJ_BOT_WORKS.md](HOW_INFJ_BOT_WORKS.md)  
- Terms for credentials and scope: [SECURITY.md](../SECURITY.md)  
