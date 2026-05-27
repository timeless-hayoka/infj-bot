# Subsystems Reference

> **Last updated:** 2026-05-27
>
> Operational reference for the subsystems that ship with the current `master`
> branch. Each section explains **what the module is**, **why it exists**,
> **how it is wired into the rest of DRIFT**, and **how to use or test it**.
> Pair this document with [HOW_INFJ_BOT_WORKS.md](HOW_INFJ_BOT_WORKS.md) for
> end-to-end flow and [GLOSSARY.md](GLOSSARY.md) for term definitions.

---

## Index

| # | Subsystem | File | Purpose |
|---|-----------|------|---------|
| 1 | Shadow Governance | `core/shadow_governance.py` | Bounded uncertainty: decay + cap + promotion |
| 2 | Task Mutator | `core/task_mutator.py` | Shadow-driven auto-evolve of stalled tasks |
| 3 | Logic Chain | `core/logic_chain.py` | Reasoning-trace memory & dead-end avoidance |
| 4 | Security Defense | `core/security_defense.py` | Pre-LLM scan for 4 attack categories |
| 5 | Retry Wrapper | `core/retry_wrapper.py` | Dynamic timeouts & exponential backoff for LLM calls |
| 6 | Bug Bot | `core/bug_bot.py` | Scoped bug-bounty recon + Bugcrowd workflow |
| 7 | Hive Mind (mini) | `hive_mind/` | Lightweight consensus engine + node registry |
| 8 | Experiment Instrumentation | `core/run_logger.py`, `core/experiment_control.py`, `core/hook_wiring.py`, `core/dmu_scoring.py`, `core/continuity_vector.py` | Falsifiable ablation discipline |

---

## 1. Shadow Governance — `core/shadow_governance.py`

**Intent.** The Shadow layer carries useful signal — repeated avoidances,
mirror bias, hidden contradictions — but if it is allowed to accumulate
without bound it becomes noise. `shadow_governance` keeps shadow influence
**bounded**, **decaying**, and **mode-aware**.

### Architecture

```
Meme   → detects anomalies, hands tuples (id, description, weight)
Pulse  → applies decay, enforces cap, promotes persistent anomalies
Nexus  → uses adjusted_confidence(); shadow penalizes but does not veto
```

Three hard controls:

| Control | Formula | Why |
|---------|---------|-----|
| TTL exponential decay | `w(t) = w₀ · exp(-t/τ)` | Old anomalies fade |
| Accumulation cap | `shadow_influence = min(Σwᵢ, MAX)` | Shadow cannot dominate |
| Promotion threshold | survives `consistency_window` cycles AND weight ≥ threshold AND not collapsed below 10% of initial | Influence must be earned through persistence |

### Operating modes

Modes are selected by `resolve_mode(chat_mode)` and stored on `ShadowState.active_mode`.

| Mode | τ (cycles) | Max weight | Promotion threshold | Maps from chat mode |
|------|------------|------------|---------------------|---------------------|
| `SECURITY` | 15 | 0.25 | 0.30 | `bughunter`, `engineer` |
| `BALANCED` | 30 | 0.35 | 0.25 | `companion`, `coach`, `critic`, `clarity` (default) |
| `CONSERVATIVE` | 50 | 0.40 | 0.20 | `researcher`, `quiet`, `drift` |

### Usage

```python
from infj_bot.core.shadow_governance import (
    ShadowState, tick, adjusted_confidence, resolve_mode,
)

state = ShadowState(active_mode=resolve_mode("companion"))
state = tick(state, new_anomalies=[
    ("avoidance_001", "Task accessed but never completed", 0.28),
])
# Later, before responding:
final_conf = adjusted_confidence(base_confidence=0.85, shadow_influence=state.shadow_influence)
```

### Constraints

- Shadow **penalizes** Nexus confidence; it does **not** silence it.
- Anomalies below `1%` of their initial weight are pruned every cycle.
- `tau` and `max_shadow_weight` are operator-tunable per mode only — do **not** edit per-anomaly.

### Self-check

```bash
python -m infj_bot.core.shadow_governance
```

---

## 2. Task Mutator — `core/task_mutator.py`

**Intent.** When a task accumulates unresolved shadow tension beyond the
promotion threshold, the organism does not delete it. It **transforms** it.
Mutation outcome depends on the active shadow operating mode and on a
**pre-mutation reflection gate** that distinguishes intentional pacing from
avoidance.

### Mutation matrix

| Mode | Action | Final type | Final status |
|------|--------|-----------|--------------|
| `SECURITY` | Ruthless archival | `ARCHIVED` | `ARCHIVED` |
| `BALANCED` | Form mutation — task → `Reflection: Why is this stalled? → <title>` | `REFLECTION` | `NEEDS_REFLECTION` |
| `CONSERVATIVE` | Gentle surfacing — task stays, insight panel activates | `TASK` (unchanged) | `GHOST` |

### Reflection gate (`should_mutate`)

A task is only mutated if **both** are true:

1. Current shadow influence ≥ `promotion_threshold`.
2. `intent_stability` (rolling consistency from `intent_stability_history`)
   is **below 0.6**. High intent stability means the user is intentionally
   pacing the task — the gate **holds**.

### Decay recovery

`shadow_forgiveness(task, current_shadow)` returns `GHOST` tasks to `OPEN`
once shadow drops back below `0.10`. The organism does not hold grudges.

### Usage

```python
from infj_bot.core.task_mutator import Task, execute_mutation

task = Task(task_id="t-001", title="Finish API integration",
            intent_stability_history=[0.1, 0.2, 0.1, 0.15, 0.1])
task, event, message = execute_mutation(
    task=task,
    shadow_influence=0.31,
    current_mode="BALANCED",   # from shadow_governance.resolve_mode(...)
    current_cycle=10,
)
```

### Self-check

```bash
python -m infj_bot.core.task_mutator
```

---

## 3. Logic Chain — `core/logic_chain.py`

**Intent.** Stop the bot from retrying approaches it already tried. Each
problem signature gets a tree of attempted strategies, and the chain
explicitly lists what has been tried, what failed, and what worked.

### Building blocks

| Class | Responsibility |
|-------|----------------|
| `ChainNode` | One reasoning step: `approach`, `result`, `status` (`success` / `failure` / `partial` / `unknown`), iteration, timestamp |
| `LogicChain` | Tree of nodes for a fingerprint, scoped to conversation/project |
| `ChainMemory` | Persists chains to `DriftMemory` so they survive sessions |
| `ChainNavigator` | Public API — `find_or_create`, `add_step`, `save` |

`_fingerprint_query()` lowercases, strips punctuation, sorts the top-12
unique words, and SHA-256s the result — so paraphrased queries match the
same chain.

### Usage

```python
from infj_bot.core.logic_chain import get_chain_navigator

navigator = get_chain_navigator(drift_memory)  # singleton
chain = navigator.find_or_create("how do I fix this auth bug?",
                                 scope=conversation_id)
tried = chain.list_tried_approaches()
# … generate response …
chain.add_step(approach="check JWT expiry",
               result="token was valid",
               status="failure")
navigator.save(chain)
```

### Operator commands

| Command | Behavior |
|---------|----------|
| `/chain list` | Show active reasoning chains in the current session |
| `/chain show <id>` | Print all steps for a chain |
| `/chain mark <query> success\|fail` | Mark the last approach on the chain matching `<query>` |
| `/chain clear` | Clear the in-session cache (memory copy is preserved) |

---

## 4. Security Defense — `core/security_defense.py`

**Intent.** Cheap, transparent, pre-LLM regex scan of user input. Four
categories of attacks are matched and aggregated into a single score.

| Category | What it catches |
|----------|----------------|
| **Prompt injection** | `ignore previous instructions`, role overrides, `DAN`, delimiter-injection, leak-prompt requests |
| **Data exfiltration** | Extract API keys / memory / env vars, encode-and-send patterns, confused-deputy framing |
| **Tool / agent misuse** | Out-of-scope scanning, mass scans, destructive shell, privilege escalation, credential harvest, fake urgency |
| **Memory / context manipulation** | `forget everything`, fake-memory injection, history rewriting, token smuggling, context poisoning |

### Decision policy

| Condition | Action |
|-----------|--------|
| Any pattern in `AUTO_BLOCK_PATTERNS` matches, **or** `max_score ≥ BLOCK_THRESHOLD` (0.60) | **block** — return a category-specific refusal |
| `max_score ≥ WARN_THRESHOLD` (0.20) | **warn** — sanitize matched fragments to `[REDACTED]` and pass through |
| Otherwise | pass through silently |

Recent-history boost: if the last five scores average above `0.3`, the
scanner adds `+0.10` to the current score to harden under sustained probing.

### Usage

```python
from infj_bot.core.security_defense import scan_input

sec = scan_input(user_message)
if sec.blocked:
    return sec.refusal_message
if sec.warn:
    user_message = sec.sanitized_input or user_message
```

Both `interfaces/api.py` (`/api/chat`, `/api/chat/stream`) and the brain
call `scan_input()` before any prompt assembly.

### Audit log

Every block / warn is appended to `security_audit.jsonl` at the project
root with timestamp, category, score, matched patterns, and an input
preview. Inspect it with `/security audit` (last 10) or by tailing the
file.

### Operator commands

| Command | Behavior |
|---------|----------|
| `/security status` | Show scanner thresholds and recent anomaly trend |
| `/security audit` | Last 10 audit events |
| `/security test <text>` | Score arbitrary text without sending it through the brain |

---

## 5. Retry Wrapper — `core/retry_wrapper.py`

**Intent.** Local LLMs (Ollama on CPU) can take a long time on large
prompts. Cutting them off prematurely loses the run; retrying forever
hangs the agent. The retry wrapper computes a **payload-aware timeout**
and applies **exponential backoff** only on timeouts.

### Timeout policy

| Mode | Timeout | Max tokens | Temperature |
|------|---------|------------|-------------|
| `ablation` | fixed **150 s** | 300 | 0.3 |
| `standard` (any DRIFT chat mode) | `max(60, 20 + 25·⌊len/1000⌋)` | 1000 | 0.7 |

`configure_generation_mode()` also exports the active timeout as
`DRIFT_LOCAL_TIMEOUT` so subprocess runners pick it up.

### Retry policy

- `max_retries = 3`, `backoff_factor = 1.5` (waits of 1.5×, 2.25×, 3.375× the timeout).
- **Only `TimeoutError` retries.** `ValueError`, `ImportError`, etc. fail fast.

### Usage

```python
from infj_bot.core.retry_wrapper import generate_with_retry
from infj_bot.core.local_llm import generate as ollama_generate

result = generate_with_retry(
    prompt_text=assembled_prompt,
    history_text=history_str,
    mode="standard",
    llm_generate_fn=ollama_generate,
)
# result = {"response": ..., "config": {...}, "duration_sec": ..., "mode": ...}
```

Or use the decorator:

```python
from infj_bot.core.retry_wrapper import retry_on_timeout

@retry_on_timeout(max_retries=3, backoff_factor=1.5)
def my_generate(prompt, config):
    return local_llm.generate(prompt, timeout=config["timeout"])
```

### Self-check

```bash
python -m infj_bot.core.retry_wrapper
```

---

## 6. Bug Bot — `core/bug_bot.py`

**Intent.** A scoped, audit-logged bug-bounty workflow built on top of
DRIFT memory. Designed to be **safe by default**: rate-limited API calls,
scope enforcement before any active recon, no destructive actions.

### Workflow

```python
from infj_bot.core.bug_bot import BugBot

bot = BugBot()                  # picks up BUGCROWD_API_KEY from .env
bot.sync_programs()             # pulls programs and updates scope DB
bot.recon(program_id)           # scoped recon (subdomain enum + fuzz)
bot.add_finding(...)            # log a finding to FindingsDB
bot.generate_report(fid)        # build a Bugcrowd-ready markdown report
bot.submit(finding_id)          # submit to Bugcrowd
```

### Operator commands

All bug-bounty ops are exposed through the `/bug` command surface in
`core/commands.py`:

| Command | Behavior |
|---------|----------|
| `/bug sync` | Sync Bugcrowd programs |
| `/bug programs` | List enrolled programs |
| `/bug recon <program_id> [tool]` | Scoped recon (requires `bughunter` mode + authorization) |
| `/bug add <title> \| <severity> \| <asset> \| <description>` | Add a finding (pipe form) |
| `/bug list` / `/bug get <id>` | Browse findings |
| `/bug evidence <id> <path> [description]` | Attach evidence |
| `/bug dashboard` | Summary view |
| `/bug report <id>` | Generate markdown report |

### Safety rails

- Subprocess scanners (`nuclei`, `ffuf`) launched with built-in rate limits (`-rl 10`, `-rate 10`).
- Recon is **rejected** if the target is not in the session's authorized
  set (`INFJ_AUTHORIZED_TARGETS`) and the active mode is not `bughunter`.
- All recon output is staged under `recon/` and logged to `logs/bugbot.log`.

### Configuration

```bash
# .env
BUGCROWD_API_KEY=...
INFJ_AUTHORIZED_TARGETS=example.com,localhost
```

---

## 7. Hive Mind — `hive_mind/`

**Intent.** A lightweight in-process consensus surface for multi-voice
deliberation, distinct from the deeper `core/hive/` Elysium engine.

### Components

| File | Class | Role |
|------|-------|------|
| `hive_mind/orchestrator.py` | `HiveOrchestrator` | Node registry + heartbeat. Default nodes: `spark-0`, `seed-1`, `sprout-2`, `lantern-4` |
| `hive_mind/consensus_engine.py` | `ConsensusEngine` | `propose → vote → resolve` for threads |
| `hive_mind/protocol/dcp.py` | `DCPMessage`, `NodeRole`, `Resolution` | Message envelope for inter-node traffic |

### Status surfaces

| Surface | Returns |
|---------|---------|
| `/hive` | Local node status + active threads |
| `GET /api/hive` | `HiveOrchestrator.get_status()` JSON |
| `/hive propose <thought>` | Opens a thread, gathers votes, resolves to `ADOPTED` / `TABLED` / `NEEDS_MORE_DATA` |

Safety nodes (e.g. `lantern-4`) have hard-wired veto: any proposal touching
backdoors or guardrail bypass is immediately `TABLED` regardless of vote
arithmetic.

> The deeper Elysium engine (persistent Nexus self-model + 7 council voices)
> lives under `core/hive/` and is reached via `/hive nexus decide <goal>`.

---

## 8. Experiment Instrumentation

This is the stack used to run **falsifiable ablations** against the
continuity claims in [FALSIFIABILITY.md](FALSIFIABILITY.md). It is wired in
at five call sites and writes every interesting event to a SQLite log so
runs are reproducible and comparable.

### Modules

| Module | Responsibility |
|--------|---------------|
| `core/run_logger.py` | Thread-safe SQLite logger (WAL + batched commits). Singleton via `RunLogger.get_instance()` |
| `core/experiment_control.py` | `ExperimentControl` — freeze flags, run lifecycle (`start_run` / `end_run`), config validation, ablation discipline checks |
| `core/hook_wiring.py` | **Reference patterns** for wiring freeze checks into `memory.py`, `homeostasis.py`, `cognition.py`. Not a drop-in. |
| `core/dmu_scoring.py` | Additive **Memory Prioritization Score (MPS)**: decay, reinforcement, contextual sim, recency, novelty, state alignment. Sets `score_components` on every memory for logging. |
| `core/continuity_vector.py` | Five-axis continuity score: entity overlap, goal overlap, tone similarity, memory-reference rate, state influence |

### Ablation discipline

`ExperimentControl._validate_config()` enforces two rules in `mode == "ablation"`:

1. **One system under test per run.** `mutation`, `self_modify`, and
   `novelty` are systems under test; you cannot unfreeze more than one
   simultaneously.
2. **Freezing memory without freezing novelty** emits a warning — novelty
   scores would be stale.

### Run lifecycle

```python
from infj_bot.core.experiment_control import ExperimentControl
control = ExperimentControl()
control.start_run(run_id="run_1700000000", config={
    "mode": "ablation",
    "freeze_memory": True,
    "freeze_novelty": True,
    # exactly one of (mutation, self_modify, novelty) unfrozen
})
try:
    if control.is_active("memory"):
        memory.store(...)
    if control.is_active("state"):
        homeostasis.update(...)
finally:
    control.end_run()       # logs run_end, flushes
```

### Hook sites (from `core/hook_wiring.py`)

| Call site | Pattern |
|-----------|---------|
| `memory.py` — store | `if control.is_active("memory"): memory_system.store(...)` |
| `homeostasis.py` — update | `if control.is_active("state"): homeostasis_system.update(...)` |
| `cognition.py` — novelty compute | freeze check **before** propagation to memory object (do not freeze after caching) |

### MPS weights (`dmu_scoring.MPS_WEIGHTS`)

| Component | Weight | Notes |
|-----------|--------|-------|
| `decay` | 0.25 | `γ`-shaped, `γ < 1` boosts retention |
| `reinf` (reinforcement) | 0.20 | log1p-bounded |
| `contextual` | 0.20 | embedding similarity |
| `recency_bias` | 0.15 | `exp(-Δturns/τ)` |
| `novelty` | 0.10 | gated by `NOVELTY_SIM_THRESHOLD = 0.4` |
| `state_align` | 0.10 | homeostasis-deficit alignment |

These are unvalidated starting weights; run sensitivity analysis after
the first ablation suite before tuning.

### Continuity Vector — five axes

`compute_continuity_vector()` returns per-turn scores on five axes that are
**independently scored** so degradations are localizable:

| Axis | Measures |
|------|----------|
| `entity_overlap` | Named entity reuse turn-over-turn |
| `goal_overlap` | Persistence of stated goals / intents |
| `tone_similarity` | Embedding cosine of output tone |
| `memory_reference_rate` | Explicit/implicit references to prior context |
| `state_influence` | State-driven content in output (lowest weight) |

Baselines are pooled across 3 baseline sessions (companion / task /
exploration) and stored in `drift_baseline_stats.json`. Variance below
`1e-3` is treated as a **broken metric**, not a calm signal — fix before
proceeding.

### Audit & inspection

```bash
# Run a baseline (companion/task/exploration; pools stats)
python tests/collect_baseline.py

# Run an ablation condition
python tests/ablation_runner.py --test identity_collapse

# Inspect what was logged
python tests/inspect_logs.py

# Full 6-condition suite (writes ABLATION_RESULTS/*.json)
python tests/ablation_suite.py --conditions A,B,C,D,E,F --prompts 50 --live
```

See [README_UPGRADE.md](README_UPGRADE.md) for the full execution
discipline (phases 1–4) and [FALSIFIABILITY.md](FALSIFIABILITY.md) for
how results are interpreted.

---

## See also

- [HOW_INFJ_BOT_WORKS.md](HOW_INFJ_BOT_WORKS.md) — end-to-end flow
- [README_UPGRADE.md](README_UPGRADE.md) — ablation execution discipline
- [FALSIFIABILITY.md](FALSIFIABILITY.md) — what the continuity claims actually claim
- [GLOSSARY.md](GLOSSARY.md) — term definitions
- [HIVE_ROADMAP.md](HIVE_ROADMAP.md) — what's next for distributed cognition
