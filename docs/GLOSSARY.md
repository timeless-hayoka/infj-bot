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
Baars-inspired attention spine, implemented as a **tiered competition**: every cycle, all submissions plus surviving items are re-ranked by current (time-decayed) salience and assigned to **Spotlight → Active → Preconscious bands → Archived** tiers. Persisted via **`workspace.db`**. See [TIERED_ATTENTION.md](TIERED_ATTENTION.md) for the full model, tier capacities, and the lifecycle of a submission.

### Spotlight / Active / Preconscious / Archived  
The four tiers of the workspace. **Spotlight** is the single highest-salience item right now (drives prompt focus and the DII *ignition* component). **Active** (capacity 5) is the rest of the consciously available set. **Preconscious** (capacity 20 across `strong` / `moderate` / `faint` / `trace` bands) is below-threshold material kept out of focus rather than discarded. **Archived** items have decayed below `ARCHIVE_THRESHOLD` (0.05) and live only in `workspace.db.workspace_history`.

### `Broadcast`  
The dataclass submitted into the workspace: `source`, `content`, base `salience`, optional `emotion_tag` + `intensity`, and a `timestamp` used for real-time exponential decay. Use `broadcast.current_salience()` rather than the raw attribute when ranking.

### Hive Mind (`hive_mind/` package)  
Local-first kernel for the distributed-cognition layer: **`HiveOrchestrator`** (node registry), **`ConsensusEngine`** (thread state machine), and the **DCP** protocol module. Wired into the bot through `core/coordination.py` and exposed via `/hive` slash commands and `/api/hive`. Heavier orchestration (Elysium, Nexus, Council) lives separately in `core/hive/`. See [HIVE_MIND.md](HIVE_MIND.md).

### Distributed Cognition Protocol (DCP)  
The message format used by the hive kernel — `DCPMessage` (with `NodeRole` and `Resolution` enums) in `hive_mind/protocol/dcp.py`. Every proposal, vote, and resolution is expressed as a `DCPMessage`.

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
- Attention model deep-dive: [TIERED_ATTENTION.md](TIERED_ATTENTION.md)  
- Hive kernel: [HIVE_MIND.md](HIVE_MIND.md) · roadmap: [HIVE_ROADMAP.md](HIVE_ROADMAP.md)  
- Terms for credentials and scope: [SECURITY.md](../SECURITY.md)  
