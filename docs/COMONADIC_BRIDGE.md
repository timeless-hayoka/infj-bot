# Comonadic Workspace Bridge

> Code: `core/context_engine.py`, `core/cognitive_ops.py`, `core/cognitive_snapshot.py`,
> `interfaces/comonad_cli.py`, `interfaces/main.py` (`--comonadic` flag).
> Tests: `tests/test_comonad.py` (16 cases).

The **Comonadic Workspace Bridge** is an alternative cognitive pipeline that runs
DRIFT's per-turn reasoning as a chain of pure, state-aware functions over an
immutable `CognitiveState`. It replaces the default `execute_cli_cycle` (PEDI
Fly-By-Wire) path with a small functional pipeline that is easier to reason about,
fork into parallel branches, and snapshot for diagnostics.

It is **opt-in** — the standard pipeline is used unless `--comonadic` is passed
to `interfaces/main.py`.

---

## Why a comonad

A regular function `f(state) -> state` loses information: it cannot consult
prior history or carry an in-flight value the way DRIFT's other state machines
(`Being`, `Shadow`, `Homeostasis`) need.

The bridge models a turn as a pair `(state, value)` — a comonad — where each
step receives the *whole* worker (state + value + history) and returns the next
value (and optionally a new state). This gives three properties the rest of the
codebase relies on:

| Property              | Why it matters here                                                                |
|-----------------------|------------------------------------------------------------------------------------|
| **Immutability**      | Steps cannot mutate previous states. Tests assert this directly.                   |
| **History accessor**  | `worker.history` is a read-only list of every prior `CognitiveState`.              |
| **Branching (`fork`)**| Run alternative cognitive paths from one context, then `merge` the winner back in. |

---

## Module map

```
core/context_engine.py     ── CognitiveState, CognitivePayload, Context, ContextWorker
core/cognitive_ops.py      ── pedi_regulation_step, state_conditioned_llm,
                              predicted_transition_step
core/cognitive_snapshot.py ── SnapshotLogger, TransitionComparator
interfaces/comonad_cli.py  ── standalone demo + calculate_state_diff()
interfaces/main.py         ── chat_loop wiring under the `--comonadic` flag
```

---

## Data types

### `CognitiveState` (Pydantic, all fields clamped `[0.0, 1.0]`)

| Field          | Default | Meaning                                                |
|----------------|---------|--------------------------------------------------------|
| `coherence`    | 0.8     | Internal consistency of the active thought.            |
| `resonance`    | 0.5     | Felt salience / emotional attunement.                  |
| `tension`      | 0.3     | Cognitive load and conflict pressure.                  |
| `shadow_depth` | 0.2     | Pressure from suppressed material (see `shadow.py`).   |

The first three dimensions are what `core/pedi_metrics.py` uses for identity
anchor distance (`DIMS = ("coherence", "resonance", "tension")`). `shadow_depth`
is carried by the comonad but excluded from anchor math — see
[`IDENTITY_REGULATOR.md`](IDENTITY_REGULATOR.md).

### `CognitivePayload` (Pydantic)

Each step writes to its own field instead of overwriting a single string — this
prevents the "junk drawer" effect as the pipeline grows.

| Field          | Owner                              |
|----------------|------------------------------------|
| `user_input`   | initial caller (`main.py`, CLI)    |
| `internal_log` | `pedi_regulation_step`             |
| `response`     | `state_conditioned_llm`            |
| `metadata`     | predictors, diagnostics, telemetry |

### `Context[A]` and `ContextWorker[A]`

```python
ctx = Context[CognitivePayload](state=state, value=payload)
worker = ContextWorker[CognitivePayload](ctx)
```

`ContextWorker` exposes:

| Member              | Purpose                                                                |
|---------------------|------------------------------------------------------------------------|
| `current()`         | The focused value (payload).                                           |
| `state`             | The current `CognitiveState`.                                          |
| `history`           | Read-only list of prior states (returned by copy).                     |
| `extend(op)`        | Apply an operation; returns a *new* worker, never mutates the original.|
| `fork(ops)`         | Run several ops in parallel from the same context.                     |
| `merge(branches,…)` | Pick one branch (or synthesise one) and continue.                      |

`extend` accepts two return shapes:

```python
def step(worker) -> NewPayload: ...                       # state unchanged
def step(worker) -> tuple[NewPayload, CognitiveState]: ... # state evolves
```

---

## Built-in operations (`core/cognitive_ops.py`)

### `pedi_regulation_step(worker) -> (payload, state)`

Soft dampening of extreme states before the LLM is queried. Mirrors a subset of
the production PEDI regulator. Concrete rules (single source of truth: the code):

- If `state.tension > 0.6` → subtract `0.2` from tension, `0.1` from coherence,
  log `"Tension damped, coherence slightly reduced"`.
- If `state.shadow_depth > 0.7` → add `0.3` to tension, log
  `"High shadow depth bleeding into tension"`.
- All values are clamped to `[0.0, 1.0]` after adjustments.

### `state_conditioned_llm(worker) -> payload`

The **Affective Logic Gate**. Picks a generation posture based on the current
state and writes it to `payload.response`:

| Trigger                                         | Mode                          |
|-------------------------------------------------|-------------------------------|
| `coherence > 0.6` and `tension < 0.5`           | `Strict Logical Deduction`    |
| `tension > 0.5` and `resonance > 0.4`           | `Exploratory Intuitive Leap`  |
| `shadow_depth > 0.7`                            | `Shadow-Driven Projection`    |
| otherwise                                       | `Standard Empathic`           |

The function only produces a *prompt prefix string*; the actual LLM call is made
by `brain.agent_turn(...)` after the comonadic pipeline finishes (see the
`--comonadic` block in `interfaces/main.py`).

### `predicted_transition_step(worker, predictor)`

Diagnostic-only. Runs `predictor(state)`, stashes the predicted next state in
`payload.metadata["predicted_state"]`, and returns the **actual** state unchanged
so the real pipeline continues. Used together with `TransitionComparator` below.

---

## Observability (`core/cognitive_snapshot.py`)

### `SnapshotLogger`

Captures a `CognitiveSnapshot` (step index, timestamp, full state, payload,
history depth, optional metadata) after each `extend(...)`. Bounded ring buffer
of `max_snapshots`. `write(path)` flushes to newline-delimited JSON and clears.

```python
logger = SnapshotLogger(max_snapshots=50)
logger.capture(worker, step=0)
worker = worker.extend(pedi_regulation_step)
logger.capture(worker, step=1)
logger.write(Path("data/snapshots.jsonl"))
```

### `TransitionComparator`

Compares a candidate predictor against the real transition between two states.

```python
comp = TransitionComparator()
report = comp.compare(
    before=state_t0,
    after=state_t1,
    predictor=lambda s: s.model_copy(update={"tension": s.tension - 0.2}),
)
report.accuracy_score      # 1.0 = perfect, 0.0 = worst
report.delta_error          # per-field signed error
```

`accuracy_score = max(0, 1 - sum(|delta_error|) / 4)`.

---

## Wiring in `interfaces/main.py`

Pass `--comonadic` on the command line. The chat loop then replaces the default
`_workspace.execute_cli_cycle(...)` call with this pipeline:

```python
ctx     = Context[CognitivePayload](state=cogn_state, value=payload)
worker  = ContextWorker[CognitivePayload](ctx)
worker  = worker.extend(pedi_regulation_step)
worker  = worker.extend(state_conditioned_llm)

# The post-regulation state is pushed back into physics + shadow before
# the prompt is assembled by the orchestrator.
_physics.state.resonance = worker.state.resonance
_physics.state.tension   = worker.state.tension
_shadow._state.depth     = worker.state.shadow_depth

prompt, emotion, dissonance = _orchestrator.assemble_prompt(...)
prompt = f"[System Direction: {worker.current().response}]\n{prompt}"
output = brain.agent_turn(prompt, ...)
```

After generation the loop runs a PEDI cycle check on the **final** state to
decide whether to seal the exchange to the Svalbard ledger. Hold and Correcting
states block the seal so the regulator doesn't anchor on regulated frames; see
[`IDENTITY_REGULATOR.md`](IDENTITY_REGULATOR.md).

The differential between the initial and final state is printed via
`interfaces/comonad_cli.calculate_state_diff(...)`:

```
delta_coherence: -0.10
delta_tension:   -0.20
delta_shadow_depth: 0.00
```

---

## Standalone demo

`interfaces/comonad_cli.py` runs the same pipeline end-to-end without touching
the rest of DRIFT. Useful when you want to exercise the operations in isolation
or while testing a new step:

```bash
python -m infj_bot.interfaces.comonad_cli
```

It seeds a high-tension scenario, runs `pedi_regulation_step` and
`state_conditioned_llm`, and prints the per-step state with the final drift
diff.

---

## Extending the pipeline

A new step is just a function `(worker) -> payload` or
`(worker) -> (payload, state)`. Keep three invariants to stay compatible with
the rest of the bridge:

1. **Never mutate `worker.state` in-place** — always return a new
   `CognitiveState` (use `state.model_copy(update={...})`).
2. **Write to your own `payload` field** when possible (`internal_log`,
   `response`, or a key under `metadata`). Overwriting another step's field
   silently breaks the audit trail.
3. **Clamp** any numeric field you set on `CognitiveState` to `[0, 1]`. The
   Pydantic model validates on construction, so out-of-range values raise.

`tests/test_comonad.py` is a good shape reference for new steps: it exercises
immutability, the four `state_conditioned_llm` modes, fork/merge, snapshot
capture, and the transition comparator.

---

## Known limitations

- The bridge does **not** persist `CognitiveState` to disk between turns.
  Continuity across turns currently comes from the surrounding subsystems
  (Physics, Shadow, Svalbard) that the wired code synchronises after each pass.
- Snapshots written by `SnapshotLogger` are append-only NDJSON. There is no
  rotation; long sessions should clear or rotate `snapshots.jsonl` periodically.
- `fork`/`merge` is in-process only — there is no distributed branching yet.
