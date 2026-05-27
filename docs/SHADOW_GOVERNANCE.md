# Shadow Governance, Task Mutation & Retry Wrapper

Three small but load-bearing modules added in `785698a`/`56cca2a` keep DRIFT honest under uncertainty and slow under hardware pressure. They are independent (no shared state, no shared lock) and self-checkable (`python -m infj_bot.core.<module>`), but they're documented together because they cooperate in the same outer loop:

```
shadow_governance.py  →  detect & decay shadow signal
        │
        ▼
task_mutator.py       →  transform stalled tasks once shadow earns promotion
        │
        ▼
retry_wrapper.py      →  protect the generation step from local-LLM timeouts
```

---

## 1. `core/shadow_governance.py` — Bounded Uncertainty

Shadow here is **unresolved contradiction held under time pressure**. It carries signal but compounds into noise if left unmanaged. This module is the policy layer that decides what counts, how fast it fades, and when it earns the right to penalize confidence.

### Three hard controls

| Control | Formula / value | Purpose |
|---------|-----------------|---------|
| **TTL exponential decay** | `w(t) = w₀ · exp(-t/τ)` | Old anomalies fade without manual cleanup |
| **Accumulation cap**      | `shadow_influence = min(Σwᵢ, MAX_SHADOW_WEIGHT)` | One layer can never silence the system |
| **Promotion threshold**   | survives `consistency_window` cycles **and** weight ≥ `promotion_threshold` | Persistence is required before signal counts |

### Operating modes

Shadow has three modes selected by the active DRIFT chat mode (`MODE_ALIAS`):

| Mode | τ (cycles) | max weight | promote @ | window |
|------|-----------:|-----------:|----------:|-------:|
| `SECURITY`     | 15 | 0.25 | 0.30 | 3 |
| `BALANCED` *(default)* | 30 | 0.35 | 0.25 | 5 |
| `CONSERVATIVE` | 50 | 0.40 | 0.20 | 7 |

Chat-mode → shadow-mode mapping (excerpt — see `MODE_ALIAS`):

```
bughunter, engineer    → SECURITY
companion, coach,      → BALANCED
critic, clarity
researcher, quiet, drift → CONSERVATIVE
```

### Public surface

```python
from infj_bot.core.shadow_governance import (
    ShadowState, ShadowAnomaly,
    tick, compute_shadow_influence, adjusted_confidence,
    resolve_mode, SHADOW_MODES,
)

state = ShadowState(active_mode=resolve_mode("companion"))
state = tick(state, new_anomalies=[
    ("avoidance_001", "Task touched but never completed", 0.28),
])
state = tick(state)            # advance with no new input
confidence = adjusted_confidence(0.85, state.shadow_influence)
```

Per cycle, `tick()`:

1. increments `current_cycle`,
2. registers new anomalies coming from the Meme/observer layer,
3. evaluates promotions (`should_promote`) and appends to `state.promoted_anomalies`,
4. **prunes** anything below 1% of its initial weight,
5. **recomputes** total `shadow_influence` with the active cap.

### Confidence semantics

Shadow **penalizes** but does **not veto** — `adjusted_confidence(base, influence) = base · (1 - influence)`. Even at the BALANCED cap of 0.35, a Nexus decision with 0.85 base confidence emerges at 0.55, not zero. The veto remains with Ethos, not Shadow.

### Run the self-check

```bash
python -m infj_bot.core.shadow_governance
```

Exercises ingestion, decay across 5 cycles, promotion, adjusted confidence, and the SECURITY-mode fast cleanse path.

---

## 2. `core/task_mutator.py` — Auto-Evolve

Once shadow earns promotion on a task, `task_mutator` transforms the task rather than deleting it. The behavior depends on the active shadow mode:

| Mode | Action | Resulting `task_type` / `status` |
|------|--------|-----------------------------------|
| `SECURITY`     | **Ruthless archival** — clear the field | `ARCHIVED` / `ARCHIVED` |
| `BALANCED`     | **Form mutation** — task becomes a reflection note | `REFLECTION` / `NEEDS_REFLECTION` |
| `CONSERVATIVE` | **Gentle surfacing** — task stays, insight panel activates | unchanged / `GHOST` |

### Pre-Mutation Reflection Gate

`should_mutate()` is run before any transformation. It returns `False` if **either**:

- `shadow_influence < promotion_threshold` (no signal to act on), or
- `calculate_intent_stability(task) > 0.6` — the user has shown a stable, intentional pacing pattern on this task across recent cycles.

This is what separates *avoidance* (low stability, mutation warranted) from *long-arc work* (high stability, hands off).

Intent stability is the rolling mean of `task.intent_stability_history` over the last 10 entries; below 3 entries the gate defaults to a moderate `0.5` (benefit of the doubt).

### Auditability

Every mutation produces a `MutationEvent` and appends to `task.mutation_log` — original title/type/status, new title/type/status, trigger mode, shadow influence, intent stability, cycle, ISO timestamp, and a `reasoning` string. There is no silent transformation.

### Forgiveness

`shadow_forgiveness(task, current_shadow, threshold=0.10)` flips a `GHOST` task back to `OPEN` and clears `insight_flag` once shadow has decayed below threshold. The mutation log records the forgiveness step so the arc is traceable.

```python
from infj_bot.core.task_mutator import execute_mutation, Task

mutated, event, message = execute_mutation(
    task=Task(task_id="t-001", title="Finish API Integration",
              intent_stability_history=[0.1, 0.2, 0.1, 0.15, 0.1]),
    shadow_influence=0.31,
    current_mode="BALANCED",
    current_cycle=10,
)
```

### Run the self-check

```bash
python -m infj_bot.core.task_mutator
```

Verifies all three modes plus the gate-holds-on-high-stability case.

---

## 3. `core/retry_wrapper.py` — Dynamic Timeouts & Exponential Backoff

Local Ollama generation on CPU-only hardware is the dominant failure mode for long prompts. `retry_wrapper.py` is the **timeout policy** for that path.

### Dynamic timeout

```
timeout = max(60s, 20s + 25s · floor(prompt_length / 1000))
```

- Floor at 60s regardless of payload size.
- ~25s budget for every additional 1k characters.
- Stored in `os.environ["DRIFT_LOCAL_TIMEOUT"]` so the local runner can pick it up.

### Modes

| Mode | timeout | max_tokens | temperature | top_p |
|------|--------:|-----------:|------------:|------:|
| `ablation` | fixed **150s** | 300 | 0.3 | 0.9 |
| `standard` | dynamic | 1000 | 0.7 | 0.95 |

`configure_generation_mode(mode, prompt_text, history_text)` returns the resolved dict and sets the env var in one call.

### Retry policy

`@retry_on_timeout(max_retries=3, backoff_factor=1.5)`:

- Retries **only** on `TimeoutError`.
- Backoff: `timeout · 1.5^attempt` — so a 60s timeout waits 60s, 90s, 135s between successive retries.
- Non-timeout exceptions (`ValueError`, `ImportError`, anything else) **fail fast** by design — retry only what retry can fix.
- Emits `[RETRY]` / `[SUCCESS]` / `[TIMEOUT]` / `[FAIL]` lines to stdout for visibility.

### Plugging in a real backend

`generate_with_retry()` accepts an `llm_generate_fn` keyword. Wire it to the real local backend:

```python
from infj_bot.core.retry_wrapper import generate_with_retry
from infj_bot.core.local_llm import generate as ollama_generate

result = generate_with_retry(
    prompt_text=assembled_prompt,
    history_text=history_text,
    mode="standard",
    llm_generate_fn=ollama_generate,
)
# result: {"response": str, "config": {...}, "duration_sec": float, "mode": str}
```

Without `llm_generate_fn`, the function returns a `"[PLACEHOLDER]"` response — useful for unit-testing the retry shell without a model.

### Run the self-check

```bash
python -m infj_bot.core.retry_wrapper
```

Validates dynamic timeout scaling, ablation-mode pins, standard-mode dynamic timeout, and the full pipeline without an LLM.

---

## Why these three together

The Apollo-11-1202 analogy in the module docstrings is the operating thesis: under load, **drop low-priority work, protect the critical path, and leave an audit trail**. Shadow Governance is the *priority drop* (anomalies decay), Task Mutator is the *path protection* (tasks transform instead of festering), and Retry Wrapper is the *critical-path guarantee* (generation has a budget and a retry policy). All three log enough state for the post-mortem to be machine-readable.

---

## Related docs

- [HOW_INFJ_BOT_WORKS.md](HOW_INFJ_BOT_WORKS.md) — where these modules sit in the cycle
- [FALSIFIABILITY.md](FALSIFIABILITY.md) — measurement discipline for these signals
- [CONTINUITY_VECTOR.md](CONTINUITY_VECTOR.md) — `shadow_influence` feeds the novelty axis
