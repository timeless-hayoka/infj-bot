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
Primary LLM wrapper in **`brain.py`**: Gemini (and optional Ollama fallback), streaming, tooling hooks where enabled. The current implementation class is `DriftBrain`; `InfjBrain` is the historical name.

### **`InfjMemory`**  
Chroma-backed memory in **`memory.py`**: save interactions after **secret scrubbing**, hybrid search/top‑k, optional document sidecar integrations. The current implementation class is `DriftMemory`.

### **"Jude" / user-facing name**  
Default narrative name for the human in prompts and seeded content. Replace in your fork if needed.

### **Logic Chain** (`core/logic_chain.py`)  
Tree of `ChainNode` reasoning steps per **query fingerprint**. Tracks approaches the bot has already tried (`success` / `failure` / `partial`) so it doesn't loop on dead-end strategies. Operator surface: `/chain list|show|mark|clear`. See [SUBSYSTEMS.md](SUBSYSTEMS.md#3-logic-chain--corelogic_chainpy).

### **MPS** — Memory Prioritization Score  
Additive re-ranking score from `core/dmu_scoring.py`. Combines six weighted factors (decay, reinforcement, contextual similarity, recency bias, novelty, state alignment) into a single `[0,1]` priority. Every memory carries a `score_components` dict so retrievals are auditable. See [SUBSYSTEMS.md](SUBSYSTEMS.md#8-experiment-instrumentation).

### **Layer 1–5**  
Architectural shorthand in the README: **Interface**, **Cognition**, **Coordination**, **Memory**, **Tools & Safety**. Layers overlap in code—it is an organizational map, not a strict dependency DAG.

### **Ollama**  
Local inference path via **`OllamaBridge`** in **`local_llm.py`** when **`INFJ_USE_LOCAL_FALLBACK`** is enabled.

### **`PromptBudget`**  
Caps prompt growth by tier (core / cognitive / analysis / context) toward **`INFJ_MAX_TOTAL_PROMPT_CHARS`**.

### **Retry Wrapper** (`core/retry_wrapper.py`)  
Payload-aware timeout (`max(60, 20 + 25·⌊len/1000⌋)` s in standard mode, fixed 150 s in `ablation` mode) plus exponential backoff. Retries only on `TimeoutError`; everything else fails fast.

### **Security Defense** (`core/security_defense.py`)  
Pre-LLM regex scan for four attack categories: prompt injection, data exfiltration, tool/agent misuse, memory/context manipulation. Fail-closed at `BLOCK_THRESHOLD = 0.60`; warn-and-sanitize at `WARN_THRESHOLD = 0.20`. Every decision is appended to `security_audit.jsonl`. Operator surface: `/security status|audit|test`.

### Shadow (`shadow.py`)  
Structured **prompt-time excerpts** from **`shadow.db`**, bounded by env caps (**`INFJ_SHADOW_PROMPT_*`**). Jung-influenced metaphor; **not** diagnosis.

### **Shadow Governance** (`core/shadow_governance.py`)  
Bounded uncertainty controller for the Shadow layer. Applies exponential decay (`w(t) = w₀·exp(-t/τ)`), accumulates anomalies under a hard cap (`MAX_SHADOW_WEIGHT`), and promotes only anomalies that survive a `consistency_window`. Three modes — `SECURITY`, `BALANCED`, `CONSERVATIVE` — map from chat modes via `resolve_mode()`.

### **SQLite "state brains"**  
Many subsystems (**being**, **embodiment**, **homeostasis**, **shadow**, etc.) persist orthogonal state as **`.db`** files under **`INFJ_DATA_DIR`** or **`PROJECT_ROOT`**.

### **Task Mutator** (`core/task_mutator.py`)  
Shadow-driven `auto_evolve` for tasks. When shadow influence exceeds `promotion_threshold` and `intent_stability < 0.6`, the task is transformed according to the active shadow mode: `SECURITY` archives, `BALANCED` reframes as `Reflection: …`, `CONSERVATIVE` marks `GHOST` and surfaces an insight prompt. `shadow_forgiveness()` restores ghosted tasks when shadow decays below `0.10`.

### **Continuity Vector** (`core/continuity_vector.py`)  
Five-axis per-turn score (entity overlap, goal overlap, tone similarity, memory-reference rate, state influence) used to compute Cohen's d under freeze-mode ablation. Baselines pool across three sessions (companion / task / exploration) and live in `drift_baseline_stats.json`. Axes failing the variance floor `1e-3` are treated as broken metrics. See [FALSIFIABILITY.md](FALSIFIABILITY.md).

### **Bug Bot** (`core/bug_bot.py`)  
Bugcrowd-integrated, scope-enforced bug-bounty workflow (sync programs → recon → findings → reports → submit). Subprocess scanners are launched with built-in rate limits; recon is rejected outside `INFJ_AUTHORIZED_TARGETS` and outside `bughunter` mode. Operator surface: `/bug sync|recon|add|list|evidence|dashboard|report|submit`.

---

## Related

- Mechanics and flow: [HOW_INFJ_BOT_WORKS.md](HOW_INFJ_BOT_WORKS.md)  
- Per-module reference: [SUBSYSTEMS.md](SUBSYSTEMS.md)  
- Terms for credentials and scope: [SECURITY.md](../SECURITY.md)  
- Falsifiability & axes interpretation: [FALSIFIABILITY.md](FALSIFIABILITY.md)  
