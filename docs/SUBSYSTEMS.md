# Subsystems Reference

Operational docs for the cognitive subsystems that are easy to miss when reading the codebase top-down. Each section explains **intent**, **mechanics**, **integration points**, and **how to verify** the subsystem locally.

Companion docs:
- [HOW_INFJ_BOT_WORKS.md](HOW_INFJ_BOT_WORKS.md) — end-to-end chat turn flow.
- [GLOSSARY.md](GLOSSARY.md) — short term definitions.
- [WEB_INTERFACE.md](WEB_INTERFACE.md) — HTTP/WebSocket surface.

---

## 1. Shadow Governance — `core/shadow_governance.py`

### Intent

Shadow is **unresolved contradiction under time pressure**: a signal that the model picked up something the surface logic does not yet explain. Left ungoverned, shadow becomes noise (every minor anomaly drags confidence to zero). Governed correctly, it is a useful drag on overconfident responses.

### Mechanics

Three controls keep shadow bounded:

1. **TTL exponential decay** — `w(t) = w₀ × exp(-t / τ)`.
2. **Accumulation cap** — `shadow_influence = min(Σ wᵢ, MAX_SHADOW_WEIGHT)`.
3. **Promotion threshold** — an anomaly must persist `consistency_window` cycles **and** still exceed `promotion_threshold` after decay before it gains influence.

Three operating modes (chosen from the active DRIFT chat mode via `resolve_mode`):

| Mode | τ (decay) | max influence | promotion threshold | window | Source modes |
|------|-----------|---------------|---------------------|--------|--------------|
| `SECURITY` | 15 | 0.25 | 0.30 | 3 | `bughunter`, `engineer` |
| `BALANCED` | 30 | 0.35 | 0.25 | 5 | `companion`, `coach`, `critic`, `clarity` |
| `CONSERVATIVE` | 50 | 0.40 | 0.20 | 7 | `researcher`, `quiet`, `drift` |

`SECURITY` is the **fast cleanse** profile: short τ, high promotion bar, low cap. `CONSERVATIVE` is **reflective**: long τ, looser promotion, higher cap. `BALANCED` is the default.

### Integration

```python
from infj_bot.core.shadow_governance import (
    ShadowState, tick, adjusted_confidence, resolve_mode,
)

state = ShadowState(active_mode=resolve_mode(chat_mode))

# Each deliberation cycle:
state = tick(state, new_anomalies=[
    ("avoidance_001", "Task touched 5 times, never advanced", 0.28),
])
nexus_confidence = adjusted_confidence(base_confidence=0.85,
                                       shadow_influence=state.shadow_influence)
```

- **Meme** detects anomalies and feeds `(id, description, weight)` tuples to `tick()`.
- **Pulse** owns the per-cycle `tick()` call and selects the active mode.
- **Nexus** consumes `state.shadow_influence` via `adjusted_confidence()`. Shadow **penalizes** confidence; it does **not** veto unless Ethos explicitly allows it.

### Verification

```bash
python -m infj_bot.core.shadow_governance
```

Prints decay, cap, promotion, and mode-switching behavior. Self-check returns `[OK]` when all invariants hold.

### Notes & constraints

- Anomalies are pruned when current weight drops below 1% of `initial_weight`.
- `promoted_anomalies` is append-only; promotion is a one-way state change for the anomaly’s lifetime.
- `shadow_influence` is the **only** value Nexus reads; downstream code should not iterate over `state.anomalies` to compute confidence again.

---

## 2. Task Mutator — `core/task_mutator.py`

### Intent

When a task accumulates unresolved shadow tension above the promotion threshold, the organism does not just delete it — it transforms it. The mutator gives DriftSurface a mode-aware, audit-logged way to react to stalled tasks **without** silently dropping user intent.

### Mutation matrix

| Mode | Action | Resulting `TaskStatus` / `TaskType` | Intent |
|------|--------|-------------------------------------|--------|
| `SECURITY` | **Ruthless archival** — clear field for focused execution | `ARCHIVED` / `ARCHIVED` | Bug-hunting / engineering need a clean workspace. |
| `BALANCED` | **Form mutation** — task rewritten as a reflection note | `NEEDS_REFLECTION` / `REFLECTION` (`"Reflection: Why is this stalled? → <title>"`) | Surfaces psychological friction as inquiry instead of guilt. |
| `CONSERVATIVE` | **Gentle surfacing** — task stays, insight flag set | `GHOST` (visible, flagged) | Respect long arcs; whisper, don’t shout. |

### Pre-mutation reflection gate

Before any mutation runs, `should_mutate()` checks two questions:

1. Is `shadow_influence ≥ promotion_threshold`? If not → no mutation.
2. Is `intent_stability < 0.6`? Stability is the rolling consistency of user engagement (`Task.intent_stability_history`). High stability ⇒ user is **intentionally pacing**; the gate holds.

This means a deliberately slow long-horizon project will not get archived just because shadow accumulated on it.

### Forgiveness

`shadow_forgiveness(task, current_shadow, threshold=0.10)` restores a `GHOST` task to `OPEN` once shadow decays below threshold. The organism does not hold grudges; the audit trail in `task.mutation_log` keeps the history.

### Integration

`TaskFlow.auto_evolve` is the intended caller. Wire shape:

```python
from infj_bot.core.task_mutator import execute_mutation

task, event, message = execute_mutation(
    task=task,
    shadow_influence=shadow_state.shadow_influence,
    current_mode=shadow_state.active_mode,
    current_cycle=cycle,
    promotion_threshold=SHADOW_MODES[mode]["promotion_threshold"],
)
if event is not None:
    log_mutation_event(event)  # feeds back to shadow field as audit
```

Every mutation appends to `task.mutation_log`. Every gate hold returns a `[GATE HELD]` message — useful for tracing why a stalled task did not transform.

### Verification

```bash
python -m infj_bot.core.task_mutator
```

Runs four scenarios covering each mode plus the high-stability gate-hold path.

---

## 3. Retry Wrapper — `core/retry_wrapper.py`

### Intent

Local CPU inference (Ollama `qwen3:4b` on Omni Slim and similar hardware) routinely hits the 60s timeout wall when prompts get large. The retry wrapper protects the critical generation path without panic loops or unbounded waits.

The Apollo 11 1202-alarm analogy is on purpose: drop low-priority retries, protect the critical path, never silently corrupt state.

### Dynamic timeout

```
timeout = max(60, 20 + 25 × ⌊prompt_length / 1000⌋)
```

| Prompt length | Computed timeout |
|--------------:|-----------------:|
| 500 chars     | 60s (floor)      |
| 1,000 chars   | 60s (floor)      |
| 4,233 chars   | 120s             |
| 10,000 chars  | 270s             |

`DRIFT_LOCAL_TIMEOUT` is set as a side effect for any downstream runner that reads it.

### Two configurations

| Mode | Timeout | Max tokens | Temperature | top_p | Use case |
|------|---------|------------|-------------|-------|----------|
| `ablation` | 150s fixed | 300 | 0.3 | 0.9 | Reproducible suite runs |
| `standard` | dynamic | 1000 | 0.7 | 0.95 | Normal chat |

### Retry policy

- `max_retries = 3`, exponential backoff `1.5^attempt` × timeout.
- Only `TimeoutError` triggers a retry. Every other exception **fails fast** — retrying a `ValueError` or `ImportError` cannot fix the underlying problem.
- Each attempt prints structured `[RETRY] Attempt N/M | Timeout: Ts`; success prints `[SUCCESS] Generation completed in Ds`.

### Integration

```python
from infj_bot.core.retry_wrapper import generate_with_retry
from infj_bot.core.local_llm import generate as ollama_generate

result = generate_with_retry(
    prompt_text=assembled_prompt,
    history_text=history_text,
    mode="standard",
    llm_generate_fn=ollama_generate,
)
# result = {"response": str, "config": {...}, "duration_sec": float, "mode": str}
```

For ad-hoc functions, decorate directly:

```python
@retry_on_timeout(max_retries=3, backoff_factor=1.5)
def my_generate(prompt, config): ...
```

### Verification

```bash
python -m infj_bot.core.retry_wrapper
```

Self-check exercises dynamic scaling, ablation mode config, standard mode config, and the placeholder pipeline.

### Common pitfalls

- The decorator pulls timeout from `kwargs['config']` or the first positional `dict` argument. If you wrap a function with a different signature, pass an explicit `config={...}` so backoff sizing is correct.
- The wrapper does **not** know how to interrupt a hung Ollama HTTP request — `llm_generate_fn` must honour the `timeout` it receives.

---

## 4. Hive Mind — `hive_mind/`

### Intent

A lightweight, **in-process** distributed cognition layer. The full federated vision lives in [HIVE_ROADMAP.md](HIVE_ROADMAP.md); this package is the runtime substrate Phase 1–2 ships on. It exists so that proposals, critiques, votes, and resolutions are **auditable** instead of hidden inside a single LLM call.

### Components

| Module | Responsibility |
|--------|----------------|
| `hive_mind/protocol/dcp.py` | Distributed Cognition Protocol: `DCPMessage`, `NodeRole`, `Resolution` enums. |
| `hive_mind/orchestrator.py` | `HiveOrchestrator`: node registry + active/inactive status. |
| `hive_mind/consensus_engine.py` | `ConsensusEngine`: propose → vote → resolve threads. |

### Distributed Cognition Protocol (DCP)

```python
@dataclass
class DCPMessage:
    source_node: str
    source_role: NodeRole          # PRIMARY | CRITIC | BACKUP | OBSERVER
    content: str
    name: str = "thought"
    priority: float = 0.5
    payload: dict = field(default_factory=dict)
    message_id: str                # 8-char uuid prefix
    timestamp: str                 # ISO-8601
```

`Resolution` values: `ADOPTED`, `TABLED`, `REJECTED`, `PENDING`.

Helper constructor: `DCPMessage.thought(source_node, source_role, content, priority=0.5)`.

### Orchestrator

```python
from infj_bot.hive_mind import HiveOrchestrator

orch = HiveOrchestrator()
orch.get_status()
# {
#   "node_count": 4,
#   "active_node_count": 4,
#   "nodes": ["spark-0", "seed-1", "sprout-2", "lantern-4"],
#   "node_status": {"spark-0": "active", ...},
#   "status": "online",
# }
orch.register_node("ember-7")
orch.deregister_node("seed-1")     # sets status="inactive"; node stays in registry
```

Default node IDs reflect the seeded posture used in `web_app.py`. The orchestrator is intentionally trivial: no networking, no heartbeat thread — that lives in the consciousness loop.

### Consensus Engine

```python
from infj_bot.hive_mind import ConsensusEngine, DCPMessage, NodeRole, Resolution

engine = ConsensusEngine()
thread = engine.propose(DCPMessage.thought(
    source_node="spark-0",
    source_role=NodeRole.PRIMARY,
    content="Promote shadow anomaly avoidance_001 to influence Nexus",
))

engine.vote(thread.thread_id, voter_id="seed-1", vote="adopt")
engine.vote(thread.thread_id, voter_id="lantern-4", vote="table")

engine.resolve(thread.thread_id, Resolution.ADOPTED,
               final_position="Accepted with caveats")

engine.active_threads()  # [] — resolved threads are filtered out
```

Each resolved thread synthesizes a new `DCPMessage` with the full voting record in `payload["voting_record"]`. This is what the `/hive thread <id>` operator surface reads.

### HTTP surface

`/api/hive` (FastAPI, `interfaces/api.py`) returns `HiveOrchestrator.get_status()`. `/api/health` includes the same payload under `hive`.

### Verification

```python
from infj_bot.hive_mind import HiveOrchestrator, ConsensusEngine, DCPMessage, NodeRole, Resolution

orch = HiveOrchestrator()
assert orch.get_status()["status"] == "online"

engine = ConsensusEngine()
t = engine.propose(DCPMessage.thought("spark-0", NodeRole.PRIMARY, "test"))
engine.vote(t.thread_id, "seed-1", "adopt")
engine.resolve(t.thread_id, Resolution.ADOPTED, "ok")
assert engine.active_threads() == []
```

### Constraints

- Imports use the absolute `infj_bot.hive_mind.*` path. The package is exported as a side-channel symlink from `web_app.py` (the `_hive_path` block); see [WEB_INTERFACE.md](WEB_INTERFACE.md) for the Observatory bridge.
- No persistence: threads live in-process. The roadmap’s **Memory Integrity Layer** (Phase 3) is what will move resolutions into hive memory.
- The 4 default nodes are seed identities, not real services. Treat the registry as a typed namespace, not a service discovery system.

---

## 5. Continuity Vector — Memory · State · Novelty triad

`core/continuity_vector.py` carries **two** things that share a file:

1. The **five-axis** continuity vector used by ablations (`compute_continuity_vector`, `collect_baseline`, `validate_baselines`, `check_axis_correlation`). See [README_UPGRADE.md](README_UPGRADE.md) and [FALSIFIABILITY.md](FALSIFIABILITY.md) for the ablation playbook.
2. The **three-axis telemetry triad** — `[memory, state, novelty]` — used live every cycle to label what the organism is doing right now.

This section documents the triad, since it lacked a dedicated guide.

### Intent

The triad answers “what kind of cognition is happening this turn?” with a 3-bit vector that maps to a small set of named patterns. It is cheap to compute, cheap to log, and cheap to read on a dashboard.

### Thresholds

```python
MEMORY_NOTES_THRESHOLD     = 0      # retrieved_notes_count > this → memory active
MEMORY_DEPTH_THRESHOLD     = 5      # history_depth > this        → memory active
STATE_COHERENCE_THRESHOLD  = 0.80   # coherence_score < this      → state active
STATE_VARIANCE_THRESHOLD   = 0.15   # pulse_variance  > this      → state active
NOVELTY_SHADOW_THRESHOLD   = 0.20   # shadow_influence > this     → novelty active
NOVELTY_ENTITIES_THRESHOLD = 0      # new_entities_detected > this → novelty active
```

All thresholds live at module top and are intended to be tuned per deployment.

### Inputs (`CognitiveContext`)

| Field | Source module | Meaning |
|-------|---------------|---------|
| `retrieved_notes_count` | `core/memory.py` retrieval | how many memory rows fed this turn |
| `history_depth` | `interfaces/main.py` history | conversation depth |
| `coherence_score` | `core/homeostasis.py` (`coherence` need) | how stable internal state is |
| `pulse_variance` | `core/homeostasis.py` (variance across needs) | regulatory load |
| `shadow_influence` | `core/shadow_governance.py` `state.shadow_influence` | unresolved contradiction load |
| `new_entities_detected` | `core/metacognition.py` novel-concept counter | inbound novelty |

Populate before prompt assembly and pass to `calculate_continuity_vector(context, cycle)`.

### Pattern names

| Vector | Name | Reading |
|-------:|------|---------|
| `(1,0,0)` | COMPANION | memory anchored, stable, familiar |
| `(0,1,0)` | REGULATED | homeostasis active, no new input |
| `(0,0,1)` | EXPLORER | novelty spike, state holding |
| `(1,1,0)` | TASK | memory + regulation, known territory under load |
| `(1,0,1)` | RESONANT | memory + novelty, creative synthesis |
| `(0,1,1)` | FRONTIER | state fighting novelty, organism adapting |
| `(1,1,1)` | FULL COUNCIL | all layers engaged, maximum deliberation |
| `(0,0,0)` | QUIET | minimal cognitive load, resting state |

Patterns are read off `ContinuityVector.pattern_name()` and surface in the Observatory cards.

### Usage

```python
from infj_bot.core.continuity_vector import (
    CognitiveContext, calculate_continuity_vector,
)

ctx = CognitiveContext(
    retrieved_notes_count=mem_count,
    history_depth=len(history),
    coherence_score=homeo.coherence.current,
    pulse_variance=homeo.variance(),
    shadow_influence=shadow_state.shadow_influence,
    new_entities_detected=metacog.new_entities,
    active_mode=state.mode,
)
vec = calculate_continuity_vector(ctx, cycle=cycle_n)
log({"continuity": vec.as_dict()})  # includes pattern name
```

### Verification

```bash
python -m infj_bot.core.continuity_vector
```

Self-check exercises all eight pattern combinations.

### Constraints

- The triad is intentionally **binary per axis** — do **not** add weighted modes here. Continuous diagnostics belong in the five-axis ablation path or in dedicated metrics modules.
- Thresholds are deployment-dependent. Tune them against `collect_baseline()` output before reading patterns in production.
- The triad lives in the same file as the five-axis vector for historical reasons; if you split the module, keep both APIs importable from the original path to avoid breaking the ablation runner.

---

## See also

- [`scripts/health_check.sh`](../scripts/health_check.sh) — runs the broader smoke including shadow / homeostasis pulses.
- `python verify_architecture.py` — checks that DMU/PEDI/PhiProxy plumbing matches expectations.
- [TEST_RISKS.md](TEST_RISKS.md) — known caveats when running tests that touch these subsystems.
