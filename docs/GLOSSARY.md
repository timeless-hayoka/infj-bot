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
Baars-inspired **tiered attention system**: a salience competition runs every cycle and assigns items to **spotlight** (rank 1), **active** (ranks 2–5, included in prompt), four **preconscious bands** (`strong / moderate / faint / trace`), or **archived** (salience < 0.05, logged to SQLite and evicted). Persisted via **`workspace.db`**. See [HOW_INFJ_BOT_WORKS.md §3.5](HOW_INFJ_BOT_WORKS.md#35-global_workspacepy--tiered-attention).

### Homeostasis (module)  
Regulates simulated **needs** over time (**`homeostasis.py`** + SQLite). Influences prompts and dashboards; informal metaphor, not a medical model.

### **`INFJ_DATA_DIR`**  
If set, relocates durable state (Chroma, SQLite DBs, `history.jsonl`, audits, etc.). Code stays in **`PROJECT_ROOT`**. Keeps clones portable and avoids stuffing the repo with runtime data.

### IIT / Φ ("phi")  
**Integrated-information–inspired metrics** and qualia-axis bookkeeping computed in **`phi_council.py`** and surfaced through the `/glyph` and `/api/phi` endpoints. Computed proxies for introspection/diagnostics — not a clinical or physics claim.

### **`DriftBrain`**  
Primary LLM wrapper in **`brain.py`**: Gemini primary, **Groq / Kimi** cloud fallbacks, **Ollama** offline fallback, streaming, tooling hooks where enabled. Generation timeouts and retries are governed by `retry_wrapper.py`.

### **`DriftMemory`**  
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

### Shadow Governance (`shadow_governance.py`)  
Distinct from `shadow.py`. Implements **bounded uncertainty management** with three controls — TTL exponential decay (`w(t) = w₀·exp(-t/τ)`), accumulation cap (`MAX_SHADOW_WEIGHT`), and a promotion threshold gate. Has three operating modes (`SECURITY`, `BALANCED`, `CONSERVATIVE`) selected from the active DRIFT chat mode. Shadow **penalizes** confidence but never **vetoes**. See [SHADOW_GOVERNANCE.md](SHADOW_GOVERNANCE.md).

### Task Mutator (`task_mutator.py`)  
Once shadow earns promotion on a task, transforms it instead of deleting it: **archive** (SECURITY), **reflection note** (BALANCED), or **ghost / insight panel** (CONSERVATIVE). Gated by an `intent_stability` rolling mean so intentional long-arc work isn't mutated as avoidance. See [SHADOW_GOVERNANCE.md §2](SHADOW_GOVERNANCE.md#2-coretask_mutatorpy--auto-evolve).

### Retry Wrapper (`retry_wrapper.py`)  
Dynamic timeout calculator (`max(60s, 20s + 25s · prompt_length/1000)`) and exponential-backoff retry decorator for local LLM generation. Ablation mode pins timeout to 150s, 300 tokens, low temperature for reproducibility. See [SHADOW_GOVERNANCE.md §3](SHADOW_GOVERNANCE.md#3-coreretry_wrapperpy--dynamic-timeouts--exponential-backoff).

### Continuity Vector  
Two instruments in `core/continuity_vector.py`: a **five-axis** baseline-normalized score (`entity_overlap`, `goal_overlap`, `tone_similarity`, `memory_reference_rate`, `state_influence`) used for falsifiability tests, and a **three-axis triad** `[memory, state, novelty]` of binary hooks with named patterns (COMPANION, EXPLORER, FRONTIER, …) used for runtime telemetry. See [CONTINUITY_VECTOR.md](CONTINUITY_VECTOR.md).

### Bug Bot (`core/bug_bot.py`)  
Scope-aware bug-bounty workflow: program sync, rate-limited recon (`subfinder`, `nuclei`, `ffuf`), findings DB (SQLite), evidence attachment, markdown report builder, optional AI-enhanced drafts, and Bugcrowd submission. Exposed through the `/bug` command surface. See [BUG_BOT.md](BUG_BOT.md).

### Hive Mind (`hive_mind/` package)  
Local, in-process consensus layer: `ConsensusEngine` (`propose → vote → resolve`), `HiveOrchestrator` (node registry & heartbeat), and the **Distributed Cognition Protocol** message type (`DCPMessage`, `NodeRole`, `Resolution`). Distinct from `core/hive/` (Elysium + Nexus + Council of 7). See [HIVE_MIND.md](HIVE_MIND.md).

### DCP — Distributed Cognition Protocol  
Wire format for thoughts that cross node boundaries. Every `DCPMessage` carries `source_node`, `source_role` (`NodeRole`), `content`, `priority`, and a structured `payload`. Threads close with a `Resolution` of `ADOPTED`, `TABLED`, `REJECTED`, or `PENDING` — execution must gate on `ADOPTED`.

### Elysium (`core/hive/`)  
Deeper async deliberation engine on top of `hive_mind/`. Holds a persistent **Nexus** self-model (goals, moral stance, narrative arc, tensions) and a **Council of 7** persistent voices (Aura, Logic, Meme, Vibe, Ethos, Pulse, Nexus). Surfaces via `/hive nexus decide`, `/hive reflect`, `/hive council status`. See [`core/hive/INDEX.md`](../core/hive/INDEX.md).

### **SQLite “state brains”**  
Many subsystems (**being**, **embodiment**, **homeostasis**, **shadow**, etc.) persist orthogonal state as **`.db`** files under **`INFJ_DATA_DIR`** or **`PROJECT_ROOT`**.

---

## Related

- Mechanics and flow: [HOW_INFJ_BOT_WORKS.md](HOW_INFJ_BOT_WORKS.md)  
- Terms for credentials and scope: [SECURITY.md](../SECURITY.md)  
