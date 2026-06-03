# Comonadic Workspace Bridge

> **Source:** `core/context_engine.py`, `core/cognitive_ops.py`, `core/cognitive_snapshot.py`, `interfaces/comonad_cli.py`, plus the `--comonadic` branch in `interfaces/main.py`.
> **Status:** Implemented and test-covered (`tests/test_comonad.py`). Live behind the `--comonadic` CLI flag; the default chat loop still uses the PEDI Fly-By-Wire path through `GlobalWorkspace.execute_cli_cycle`.

---

## 1. What it is

The **Comonadic Workspace Bridge** is an alternative state-regulation pipeline for one chat turn. Instead of mutating shared singletons (physics, shadow, workspace) in place, it threads the bot's regulated cognitive state through a chain of pure functions wrapped in a comonadic container (`ContextWorker`).

Each step in the chain:

- reads the current `(state, payload)` from the worker,
- returns a *new* worker with an updated payload and optional state delta,
- automatically appends the prior state to a read-only history list.

The pipeline is immutable, branchable (`fork`/`merge`), and snapshot-friendly — making it the cleanest entry point for ablations, predictive diagnostics, and any future declarative composition of cognitive steps.

It is intentionally **decoupled** from the larger module graph (no singletons, no SQLite). It speaks only PEDI variables — `coherence`, `resonance`, `tension`, `shadow_depth` — and reads/writes a structured `CognitivePayload` so each step has its own field instead of stomping on a shared scratch string.

---

## 2. Data model

### `CognitiveState` (`core/context_engine.py`)

```python
class CognitiveState(BaseModel):
    coherence: float    # 0.0 – 1.0
    resonance: float    # 0.0 – 1.0
    tension: float      # 0.0 – 1.0
    shadow_depth: float # 0.0 – 1.0
```

All four axes are bounded `[0.0, 1.0]` via Pydantic `Field(ge=0.0, le=1.0)`. Construction raises `ValidationError` for out-of-range values (see `test_cognitive_state_validation_bounds`).

### `CognitivePayload`

```python
class CognitivePayload(BaseModel):
    user_input: str = ""
    internal_log: str = ""   # PEDI regulation writes here
    response: str = ""       # State-conditioned gate writes here
    metadata: dict = {}      # Diagnostics, predicted_state, branch tags
```

Each pipeline step writes to its own field. This is enforced by convention and verified by `test_each_step_writes_own_field`. `model_copy()` deep-copies `metadata` so mutations to a copy never leak back to the source context.

### `Context[A]` and `ContextWorker[A]`

```python
class Context(BaseModel, Generic[A]):
    state: CognitiveState
    history: list[CognitiveState]
    value: A

class ContextWorker(Generic[A]):
    def current(self) -> A: ...
    @property
    def state(self) -> CognitiveState: ...
    @property
    def history(self) -> list[CognitiveState]:
        # Returns a copy — mutating the returned list does NOT touch the worker.
        ...
    def extend(self, op) -> "ContextWorker[B]": ...
    def fork(self, ops: list[...]) -> list["ContextWorker[Any]"]: ...
    def merge(self, branches, selector) -> "ContextWorker[Any]": ...
```

`extend(op)` is the comonadic counit / cobind: it applies `op(self)` (which may return either a new payload, or a `(payload, new_state)` tuple), appends the *previous* state to `history`, and returns a fresh worker. The original worker is never mutated.

---

## 3. Built-in pipeline steps (`core/cognitive_ops.py`)

### `pedi_regulation_step(worker) -> (payload, state)`

The state-side regulator. It writes to `payload.internal_log` and produces an updated `CognitiveState`:

- `state.tension > 0.6` → damp tension by 0.2, reduce coherence by 0.1.
- `state.shadow_depth > 0.7` → bleed +0.3 into tension (shadow inflation).
- All values are clamped back into `[0, 1]`.

This is a *much* simpler, deterministic cousin of the anchor-based `PEDIEngine` in `core/pedi_metrics.py`. It exists so the comonadic pipeline can do meaningful state work without needing a Svalbard vault.

### `state_conditioned_llm(worker) -> payload`

The **Affective Logic Gate**. Reads the *current* state and writes a strategy hint to `payload.response`. Four mutually exclusive modes:

| Trigger | Mode | Prompt prefix written into `response` |
|---|---|---|
| `coherence > 0.6 and tension < 0.5` | Strict Logical Deduction | "Answer purely factually and logically." |
| `tension > 0.5 and resonance > 0.4` | Exploratory Intuitive Leap | "Answer creatively, making intuitive connections." |
| `shadow_depth > 0.7` | Shadow-Driven Projection | "Answer defensively, questioning the user's premise." |
| else | Standard Empathic | "Answer warmly and directly." |

The gate does not call any LLM. It produces a *directive* that the outer loop prepends to the real prompt before passing it to `DriftBrain.agent_turn`.

### `predicted_transition_step(worker, predictor) -> (payload, state)`

A diagnostic, no-op-on-state step. It runs `predictor(worker.state)`, stores the predicted next state under `payload.metadata["predicted_state"]`, and returns the *actual* state unchanged. Pair it with `TransitionComparator` (below) to score how well any predictor models real transitions.

---

## 4. Observability (`core/cognitive_snapshot.py`)

### `SnapshotLogger`

Captures a `CognitiveSnapshot` at any point in the pipeline:

```python
logger = SnapshotLogger(max_snapshots=50)
logger.capture(worker, step=0, extra_metadata={"op": "init"})
worker = worker.extend(pedi_regulation_step)
logger.capture(worker, step=1)
logger.write(Path("data/snapshots.jsonl"))   # appends, then clears buffer
```

- Bounded buffer (oldest dropped past `max_snapshots`).
- `write()` appends newline-delimited JSON and clears the in-memory buffer.
- Each snapshot contains: `step_index`, ISO `timestamp`, full `state` dump, `user_input`, `internal_log`, `response`, `history_depth`, and arbitrary `metadata`.

### `TransitionComparator`

Scores a predictor against the bot's actual evolution:

```python
comp = TransitionComparator()
report = comp.compare(before, after, predictor=lambda s: s.model_copy(update={"tension": s.tension - 0.2}))
print(report.accuracy_score)   # 0.0 worst → 1.0 perfect
print(report.delta_error)      # per-axis predicted - actual
```

Accuracy is `max(0, 1 - mean_absolute_error / 4)` across the four axes. `evaluate_on_history(history, predictor)` runs the comparison across every adjacent pair in a state chain.

---

## 5. Branching cognition: `fork` / `merge`

`ContextWorker.fork(operations)` applies several operations to the *same* starting context and returns a list of independent workers. `merge(branches, selector)` picks one (or synthesises a result) to continue the pipeline.

```python
branches = worker.fork([logical_path, intuitive_path])
winner = worker.merge(
    branches,
    selector=lambda bs: max(bs, key=lambda b: len(b.current().response)),
)
```

Typical use cases:

- Compare two prompt strategies in parallel and pick the longer/more coherent response.
- Run a tension-low vs. tension-high "what would I say if I felt different?" branch for self-evaluation.
- Generate predictor / actual pairs without mutating the live pipeline.

Branches never share state with each other or with the parent worker.

---

## 6. The `--comonadic` CLI flag

`interfaces/main.py` supports two paths inside its `chat_loop`:

- **Default** (`else` branch): calls `GlobalWorkspace.execute_cli_cycle(...)`, which runs the **anchor-based PEDI Fly-By-Wire** (`core/pedi_metrics.py::PEDIEngine`), Lantern-4 veto, and conditional Svalbard sealing. This is the production path.
- **Comonadic** (when `--comonadic` is in `sys.argv`): builds a `ContextWorker`, extends through `pedi_regulation_step` and `state_conditioned_llm`, threads the resulting `worker.current().response` into the prompt as `[System Direction: ...]`, then calls `DriftBrain.agent_turn`. After generation, it still consults the production PEDI engine via `_workspace.pedi.evaluate_cycle` to gate the Svalbard deposit (skipping deposit when the status starts with `HOLD` or is `CORRECTING`).

To use it:

```bash
python -m infj_bot chat -- --comonadic
# or
python -m infj_bot.interfaces.main --comonadic
```

The flag is detected with a simple `"--comonadic" in sys.argv` check, so any argv-passing invocation works. Both paths share the same downstream side effects: memory save, history append, emotional field, predictor, temporal, etc.

The comonadic path also prints a **state transition diff** after each turn:

```
[*] Comonadic Workspace Bridge active. State Transition Diff:
   delta_coherence: -0.10
   delta_tension: -0.20
```

`calculate_state_diff` (in `interfaces/comonad_cli.py`) computes the same `delta_*` keys used for vault deposits.

---

## 7. Standalone demo

`interfaces/comonad_cli.py` can be run directly as a self-contained demo (no LLM, no I/O):

```bash
python -m infj_bot.interfaces.comonad_cli
```

It seeds a high-tension `CognitiveState`, sends a probe message ("Why did you disagree with me yesterday?"), runs `pedi_regulation_step → state_conditioned_llm`, and prints the per-step state, internal log, gate directive, and final drift diff. Useful for sanity-checking the pipeline after edits to `cognitive_ops.py`.

---

## 8. How it relates to the rest of DRIFT

| Subsystem | Relationship |
|---|---|
| **`core/pedi_metrics.py::PEDIEngine`** (production PEDI) | Different implementation. The anchor-based engine reads the last 20 vault blocks to compute a center-of-gravity and applies Fly-By-Wire corrections. The comonadic `pedi_regulation_step` is a deterministic dampener with no vault dependency. The `--comonadic` flow still defers to `PEDIEngine` for the final `HOLD/CORRECTING/EVOLVING/STABLE` verdict that gates Svalbard deposits. |
| **`metrics/pedi.py::PediIndex`** (continuity PEDI) | Unrelated. Measures *fluidity across context resets* over a 7-need vector; orthogonal to the comonadic bridge. |
| **`core/svalbard_vault.py`** | The comonadic path writes to the same vault as the default path, with the same Lantern-4-style gating (skip on `HOLD_*` / `CORRECTING`, quarantine when `shadow_depth > 0.75`). |
| **`core/global_workspace.py`** | The bridge does not bypass the Global Workspace; the outer `chat_loop` still submits user input and bot output to `_workspace.submit(...)` after the comonadic pipeline completes. |
| **`core/brain.py`** | Generation still goes through `brain.agent_turn`. The bridge only changes *which directive prepends the prompt* and *which state diff is logged*. |

---

## 9. Constraints and caveats

- **No LLM inside the bridge.** `state_conditioned_llm` is misleadingly named: it only writes a *directive*; the real LLM call still happens in `brain.agent_turn`.
- **Strict 3-axis state space.** The four `CognitiveState` fields mirror what `core/pedi_metrics.py` tracks (with `shadow_depth` carried alongside but intentionally excluded from `pedi_metrics.DIMS` anchor distance — see the comment block at the top of `core/pedi_metrics.py`).
- **Immutable history.** `worker.history` returns a *copy*. Code that pokes `worker._ctx.history` will be caught in review (`test_no_private_attribute_poking`).
- **`metadata` deep-copy.** `CognitivePayload.model_copy` shallow-copies the metadata dict so mutations to a copy never leak back; do not assume nested dicts are deeply cloned.
- **No persistence layer.** The bridge itself stores nothing on disk; snapshot logging is opt-in via `SnapshotLogger.write(...)`.
- **`--comonadic` is detected via `sys.argv`.** It is not surfaced through `interfaces/cli.py` subcommand argparse yet; you must pass it as a raw arg (e.g. `python -m infj_bot.interfaces.main --comonadic`).

---

## 10. Tests

`tests/test_comonad.py` covers:

- `CognitiveState` field validation bounds.
- Immutability of `worker` and `worker.history` under `extend`.
- All four `state_conditioned_llm` mode branches.
- `pedi_regulation_step` writing `internal_log` without clobbering `response` (and vice versa).
- `fork` producing independent branches; `merge` invoking the supplied selector.
- `SnapshotLogger` capture + rotation past `max_snapshots`.
- `TransitionComparator` accuracy with perfect / imperfect predictors and across a history chain.
- `predicted_transition_step` storing `predicted_state` in `metadata` without touching the actual state.

Run with:

```bash
pytest tests/test_comonad.py -v
```

---

## 11. Extending the pipeline

To add a new step:

1. Implement a function `def my_step(worker: ContextWorker[CognitivePayload]) -> CognitivePayload | tuple[CognitivePayload, CognitiveState]:` in `core/cognitive_ops.py`.
2. **Always** start from `worker.current().model_copy()` and (if mutating state) `worker.state.model_copy()`. Never mutate in place.
3. Write to your own dedicated payload field. If you need to share data with later steps, put it under `payload.metadata`.
4. Add a focused test in `tests/test_comonad.py` mirroring the existing pattern.
5. Compose with `worker = worker.extend(my_step)` in either `interfaces/main.py` (production path) or your own driver.

If a step needs an extra argument (like `predicted_transition_step` does), wrap it: `worker.extend(lambda w: my_step(w, extra_arg))`.
