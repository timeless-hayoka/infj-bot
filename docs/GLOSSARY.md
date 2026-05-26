# Glossary

Terms below are **project-local**: they explain how this codebase names things, not universal AI or neuroscience definitions.

---

## A–Z

### ChromaDB / semantic memory  
Vector store used for **retrieved** episodic memory and related passages. Persisted under your configured data root (often `chroma_db/` beside SQLite files). Distinct from per-turn chat logs in **`history.jsonl`**.

### Cognitive plugin  
A registered module in **`cognitive_architecture.py`** that can expose a **background `cycle_*` handler**, a **`prompt_formatter`** snippet, or both. Plugins compete for limited prompt space via **`PromptBudget`**.

### Critic (`DRIFT_CRITIC_MODEL`, legacy `INFJ_CRITIC_MODEL`)
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

### **`DriftBrain`** (formerly **`InfjBrain`**)
Primary LLM wrapper in **`brain.py`**. Picks an SDK once in `__init__`
(Ollama fast-path → `google.genai` → legacy `google.generativeai` →
none), then per-call routes through **Groq → Kimi → Gemini → Ollama**
based on env toggles and key availability. Holds the system prompt for
the primary companion and the critic, manages streaming, parallel tool
execution, an in-memory + disk LRU `gen_cache`, and a `ChainNavigator`
for cross-session reasoning traces.

### **`DriftMemory`** (formerly **`InfjMemory`**)
Chroma-backed memory in **`memory.py`**: save interactions after **secret
scrubbing**, hybrid search/top‑k, optional document sidecar integrations.

### **“Jude” / user-facing name**  
Default narrative name for the human in prompts and seeded content. Replace in your fork if needed.

### **Layer 1–5**  
Architectural shorthand in the README: **Interface**, **Cognition**, **Coordination**, **Memory**, **Tools & Safety**. Layers overlap in code—it is an organizational map, not a strict dependency DAG.

### **Ollama**
Local inference path via **`OllamaBridge`** in **`local_llm.py`** when
**`DRIFT_USE_LOCAL_FALLBACK`** (or legacy `INFJ_USE_LOCAL_FALLBACK`) is
enabled. When **`DRIFT_PREFER_LOCAL`** is also true and the daemon is
reachable, `DriftBrain.__init__` short-circuits the cloud SDK setup and
serves all turns from the local model.

### **Logic Chain (`logic_chain.py`)**
A `ChainNavigator` that fingerprints each query, records the
approach/result/status for every reasoning step, detects semantic
overlap with prior attempts, and injects a `[REASONING CHAIN]` block
into the next prompt so the model does not retry a dead end. Chains
persist across sessions through `DriftMemory`. CLI commands:
`/chain list`, `/chain show <id>`, `/chain mark <q> fail`,
`/chain clear`.

### **Security Defense (`security_defense.py`)**
Pre-generation scanner that runs at three boundaries (API, CLI, and
just before the LLM call). It classifies inputs against four buckets —
prompt injection, data exfiltration, tool misuse, memory manipulation —
auto-blocks critical patterns, warns on medium-confidence ones, and
appends to `security_audit.jsonl`. See the README "Security Defense
Layer" section.

### **Continuity Vector / DII**
Three-axis telemetry (`dii_tracker.py` + `continuity_vector.py`) that
the dashboard uses to express how stable, aware, and embodied the bot
has been across recent turns. Wired into the Web UI delta-state stream.

### **Phi Council**
Background "council" of perspective voices used by Elysium for
self-reflection and proposal generation (`phi_council.py`,
`phi_proxy.py`). Marked as **background-only** by ablation Condition A
— it does not directly mutate the prompt the user sees.

### **Hive / Observatory**
External symlinked dependency under `hive_mind/` that the Web UI imports
through `drift_bridge`. When the import succeeds, the dashboard
broadcasts additional Observatory data alongside the normal SocketIO
state.

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
