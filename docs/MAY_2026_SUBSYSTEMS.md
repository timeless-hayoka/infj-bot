# May 2026 Subsystems

Four modules landed in the `feat(core)` commit
[`785698a`](https://github.com/timeless-hayoka/infj-bot/commit/785698a)
and are not yet covered in the architecture overview. They form a small
internal toolkit for bounded uncertainty, task evolution, generation
resilience, and behavioral telemetry.

| Module | One-line role |
|--------|--------------|
| [`core/shadow_governance.py`](#1-shadow-governance) | Time-decaying, mode-gated uncertainty influence — shadow whispers doubt, never vetoes |
| [`core/task_mutator.py`](#2-task-mutator) | When a task accumulates unresolved shadow, transform or archive it instead of letting it rot |
| [`core/retry_wrapper.py`](#3-retry-wrapper) | Dynamic timeout + exponential backoff for local + cloud LLM generation |
| [`core/continuity_vector.py`](#4-continuity-vector) | Telemetry for behavioral continuity: a 5-axis baseline-normalized score and a fast 3-axis `[Memory, State, Novelty]` triad |

All four are self-contained: each has a `self_check()` (or pytest module)
and no required dependency outside the standard library and `numpy`.

---

## 1. Shadow governance

`core/shadow_governance.py`

### Intent

Shadow is unresolved contradiction. Without bounds it monopolizes attention
and starves Logic/Nexus of useful signal. This module enforces three hard
controls so the Shadow layer can influence Nexus's confidence without
overriding it:

1. **TTL exponential decay** — `w(t) = w₀ × exp(-t / τ)`
2. **Accumulation cap** — `shadow_influence = min(Σ wᵢ, MAX_SHADOW_WEIGHT)`
3. **Promotion gate** — an anomaly must survive a consistency window
   before it earns influence

### Modes

Operating mode is selected by `resolve_mode(chat_mode)`, which maps DRIFT
chat modes onto one of three governance presets:

| Mode | τ (cycles) | Max influence | Promotion threshold | Consistency window |
|------|------------|--------------|---------------------|--------------------|
| `SECURITY` (`bughunter`, `engineer`) | 15 | 0.25 | 0.30 | 3 cycles |
| `BALANCED` (`companion`, `coach`, `critic`, `clarity`) — default | 30 | 0.35 | 0.25 | 5 cycles |
| `CONSERVATIVE` (`researcher`, `quiet`, `drift`) | 50 | 0.40 | 0.20 | 7 cycles |

Faster decay + lower cap in `SECURITY` cleanses the field for focused
work; slower decay + higher cap in `CONSERVATIVE` lets reflective sessions
hold open uncertainty longer.

### Data flow

```
Meme   → detects anomalies          (anomaly_id, description, weight)
Pulse  → tick(state, new_anomalies)
        - increments cycle
        - adds new anomalies
        - evaluates promotions
        - prunes dead anomalies (< 1% of initial weight)
        - recomputes shadow_influence (capped)
Nexus  → adjusted_confidence(base_confidence, state.shadow_influence)
```

`adjusted_confidence(base, infl) = max(0.0, base × (1 - infl))`.

### Minimal example

```python
from infj_bot.core.shadow_governance import (
    ShadowState, tick, adjusted_confidence, resolve_mode,
)

state = ShadowState(active_mode=resolve_mode("bughunter"))

state = tick(state, new_anomalies=[
    ("avoidance_001", "Task repeatedly accessed but never completed", 0.28),
    ("mirror_bias_002", "Consecutive agreements without challenge", 0.18),
])

for _ in range(5):
    state = tick(state)

score = adjusted_confidence(0.85, state.shadow_influence)
# score ≤ 0.85; shadow penalizes but does not silence Nexus.
```

### Constraints

- Shadow **never** vetoes. The contract is "penalize confidence", not
  "block output". Anything stronger belongs in `guardrails.py` /
  `security_defense.py`.
- Cycle counter is integer and module-local. Persist `ShadowState`
  yourself if you want continuity across process restarts.
- The "anomaly id" is the dedup key. Re-ingesting the same id does not
  bump weight — re-detection requires a new id.

---

## 2. Task mutator

`core/task_mutator.py`

### Intent

When a task accumulates shadow tension beyond the promotion threshold,
DriftSurface does **not** silently delete it. The mutator chooses one of
three responses based on the active shadow mode. Every mutation is logged
to the task and emitted as a `MutationEvent` for audit.

The flow is gated by an **intent-stability check** that distinguishes
intentional delay from avoidance:

```
shadow ≥ promotion_threshold ?
        │
        ▼
  intent_stability ≤ 0.6 ?
        │
        ▼
   choose action by mode
```

### Mutation matrix

| Active mode | Action | Resulting task state |
|-------------|--------|---------------------|
| `SECURITY` | **Ruthless archival** | `status = ARCHIVED`, `type = ARCHIVED`, insight flag `"[System: Shadow resolved — field cleared]"` |
| `BALANCED` | **Form mutation** — task → reflection note | `title = "Reflection: Why is this stalled? → <orig>"`, `type = REFLECTION`, `status = NEEDS_REFLECTION` |
| `CONSERVATIVE` | **Gentle surfacing** — task remains visible | `status = GHOST`, `insight_flag = "This carries shadow tension — want to explore?"` |

If shadow later decays below `0.10`, `shadow_forgiveness()` restores a
`GHOST` task to `OPEN` and clears the insight flag — DriftSurface does not
hold grudges.

### Public surface

```python
should_mutate(task, shadow_influence, promotion_threshold, current_cycle)
    → (proceed: bool, intent_stability: float, reason: str)

execute_mutation(task, shadow_influence, current_mode, current_cycle,
                 promotion_threshold=0.25)
    → (task: Task, event: MutationEvent | None, message: str)

shadow_forgiveness(task, current_shadow, threshold=0.10) → Task

calculate_intent_stability(task, recent_cycles=10) → float
```

### Constraints

- Intent stability requires at least 3 entries in
  `task.intent_stability_history`. Below that, the function returns `0.5`
  (benefit of the doubt) and mutation is gated open.
- `execute_mutation` mutates the `Task` object in place **and** returns
  it; treat the return value as the canonical post-state.
- Mutation events are appended to `task.mutation_log` as plain dicts.
  Persist them yourself if you want a system-wide audit trail beyond the
  in-memory task.

---

## 3. Retry wrapper

`core/retry_wrapper.py`

### Intent

Local Ollama on CPU routinely takes 30–120 s for a 3000-character prompt.
Cloud calls timeout at random times. This module gives every generation
path the same treatment:

1. **Dynamic timeout** scaled to payload size.
2. **Exponential backoff retry** on timeouts only — non-timeout errors
   fail fast.
3. **Mode-aware tuning** — `"ablation"` uses fixed, low-variance settings;
   `"standard"` (or any DRIFT chat mode) uses dynamic, normal-variance
   settings.

### Timeout policy

| Quantity | Standard mode | Ablation mode |
|----------|---------------|---------------|
| Base | 20 s | — |
| Per 1000 chars | +25 s | — |
| Floor | 60 s | — |
| Fixed timeout | — | 150 s |
| Max tokens | 1000 | 300 |
| Temperature | 0.7 | 0.3 |
| `top_p` | 0.95 | 0.9 |

`get_dynamic_timeout(prompt_length)` is the source of truth:

```
timeout = max(60, 20 + (prompt_length // 1000) * 25)
```

The computed timeout is also written to `DRIFT_LOCAL_TIMEOUT` for any
downstream worker that reads the env var.

### Retry policy

- `max_retries = 3` (so up to 4 attempts).
- `backoff_factor = 1.5` — wait grows as `timeout × 1.5 ** attempt`.
- Only `TimeoutError` triggers a retry. Every other exception is re-raised
  immediately.

### Usage

Decorator form:

```python
from infj_bot.core.retry_wrapper import retry_on_timeout

@retry_on_timeout(max_retries=3, backoff_factor=1.5)
def generate(prompt, *, timeout, **kw):
    return ollama_client.generate(prompt, timeout=timeout, **kw)
```

Convenience entry point:

```python
from infj_bot.core.retry_wrapper import generate_with_retry
from infj_bot.core.local_llm import generate as ollama_generate

result = generate_with_retry(
    prompt_text=assembled_prompt,
    history_text=conversation_history,
    mode="standard",
    llm_generate_fn=ollama_generate,
)
# result == {"response": ..., "config": {...}, "duration_sec": ..., "mode": ...}
```

### Constraints

- The decorator reads `config["timeout"]` from the first positional
  argument or `config=` kwarg. If neither is a dict, it falls back to
  `ABLATION_TIMEOUT` (150 s) for the retry wait calculation. Pass `config`
  explicitly when wrapping non-trivial generators.
- Retries are blocking (`time.sleep`). Inside a Gevent worker they yield
  via gevent's monkey patch; in a plain `threading` worker they will block
  the thread.
- The wrapper does **not** retry inside `llm_generate_fn`. Your function
  should raise `TimeoutError` (not return a partial result) for the retry
  loop to engage.

---

## 4. Continuity vector

`core/continuity_vector.py`

Two related telemetry products live in this module — pick the one that
matches your use case.

### 4.1 Five-axis behavioral continuity (offline analysis)

Used by ablation studies, identity-collapse tests, and the reintroduction
curve. Each axis is an independent measurement of behavioral continuity
across turns:

| Axis | What it measures | Notes |
|------|------------------|-------|
| `entity_overlap` | Jaccard overlap of named entities across turns | Use spaCy NER |
| `goal_overlap` | Embedding overlap of stated goals | Requires explicit goal surfacing from AgencyState |
| `tone_similarity` | Cosine similarity of tone embedding | Embed first + last sentence of each response |
| `memory_reference_rate` | Explicit/implicit references to prior context per turn | Keywords plus entity reuse not in prompt |
| `state_influence` | State-driven content in output | Weakest axis — keep its weight low |

**Workflow**:

1. Run 3 baseline sessions (`companion`, `task`, `exploration`).
2. `collect_baseline(session_data_list)` pools the runs and persists
   `drift_baseline_stats.json`.
3. `validate_baselines(stats)` warns on axes whose `std < 1e-3`. Fix the
   metric **before** running ablations — a flat axis amplifies noise when
   z-scored.
4. For each turn during an ablation, call
   `compute_continuity_vector(response_data, baselines)` to get z-scored
   per-axis scores plus the raw values.
5. After the run, `check_axis_correlation(session_axis_data)` flags axis
   pairs with `|r| > 0.6` — if two axes track each other you have a
   redundant measurement, not two.

**Operationalization notes** for hooking the axes to the live system are
inline as a module docstring at the bottom of `continuity_vector.py`.

### 4.2 Three-axis telemetry triad (live, every cycle)

`[Memory, State, Novelty]` is a fast 3-bit fingerprint of the current
cognitive cycle, intended for the Observatory dashboard and for
homeostasis state updates.

```python
from infj_bot.core.continuity_vector import (
    CognitiveContext, calculate_continuity_vector,
)

ctx = CognitiveContext(
    retrieved_notes_count=memory.last_retrieval_count,
    history_depth=len(history),
    coherence_score=homeostasis.coherence,
    pulse_variance=homeostasis.variance_across_needs(),
    shadow_influence=shadow_state.shadow_influence,
    new_entities_detected=metacognition.novel_entities_this_cycle,
    active_mode=state.mode,
)

vec = calculate_continuity_vector(ctx, cycle=current_cycle)
# vec.as_list() → [1, 0, 1]
# vec.pattern_name() → "RESONANT — memory + novelty, creative synthesis"
```

Activation thresholds (tunable constants at the top of the module):

| Axis | Active when |
|------|-------------|
| `memory` | `retrieved_notes_count > 0` **or** `history_depth > 5` |
| `state` | `coherence_score < 0.80` **or** `pulse_variance > 0.15` |
| `novelty` | `shadow_influence > 0.20` **or** `new_entities_detected > 0` |

Pattern names cover all eight combinations — `(0,0,0) QUIET` through
`(1,1,1) FULL COUNCIL`.

### Constraints

- Baseline file path (`drift_baseline_stats.json`) is **relative to the
  current working directory**. Run the collection step from the project
  root, or set the path explicitly if you split processes.
- `state_influence` is intentionally the weakest axis; do not weight it
  equally with the others in derived scores.
- The triad's activation logic is monotone in the inputs. If you change a
  threshold, re-baseline before comparing across runs.

---

## 5. How the four modules compose

In normal operation the pieces run together like this:

```
            ┌────────────────────────────────────────────────┐
            │ CognitiveOrchestrator.assemble_prompt()        │
            └───────────────┬────────────────────────────────┘
                            │
                            ▼
       shadow_governance.tick(state, new_anomalies)
                            │
                            ▼
       continuity_vector.calculate_continuity_vector(ctx, cycle)
                            │
                            ▼
       prompt assembled, telemetry published to Observatory
                            │
                            ▼
       retry_wrapper.generate_with_retry(prompt, mode=state.mode,
                                         llm_generate_fn=local_llm.generate)
                            │
                            ▼
          Nexus: adjusted_confidence(base, shadow_influence)
                            │
                            ▼
       task_mutator.execute_mutation(task, shadow_influence,
                                     current_mode=shadow_mode,
                                     current_cycle=cycle)
```

`shadow_governance` and `task_mutator` share the **mode string**
(`SECURITY` / `BALANCED` / `CONSERVATIVE`) — use `resolve_mode(chat_mode)`
to translate from the user-facing mode to the shadow mode in one place.

---

## 6. See also

- [`HOW_INFJ_BOT_WORKS.md`](HOW_INFJ_BOT_WORKS.md) — chat-turn pipeline
  the four modules plug into.
- [`DMU_PEDI_TEST_PLAN.md`](DMU_PEDI_TEST_PLAN.md) — earlier test plan for
  the dynamic memory unit / PEDI evaluation that the continuity vector
  feeds.
- [`FALSIFIABILITY.md`](FALSIFIABILITY.md) — methodology context for the
  ablation-suite consumers of `continuity_vector`.
- [`GLOSSARY.md`](GLOSSARY.md) — definitions for `Meme`, `Pulse`, `Nexus`,
  `Ethos`, and other layer names referenced above.
