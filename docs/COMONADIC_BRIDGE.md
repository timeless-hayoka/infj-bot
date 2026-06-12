# Comonadic Workspace Bridge

*Covers `core/context_engine.py`, `core/cognitive_ops.py`, and the
`--comonadic` flag in `interfaces/main.py`.*

---

## Why it exists

Most of DRIFT's cognition mutates global singletons (the workspace, the vault,
the shadow, …) as a turn flows through `execute_cli_cycle`. That is fast and
practical, but it makes it hard to:

- compose new regulation steps without touching the workspace,
- fork two candidate responses from the same starting state, or
- compare what a predictor *expected* a state to be against what it actually
  became.

The Comonadic Workspace Bridge is an **immutable, composable** pipeline that
sits next to the existing fly-by-wire path. It threads a `CognitiveState` and
a structured `CognitivePayload` through a chain of pure operations, recording
each intermediate state in a history list for diagnostics.

---

## Core types

| Type | Where | Purpose |
|------|-------|---------|
| `CognitiveState` | `core/context_engine.py` | Pydantic model of the four continuous variables PEDI cares about: `coherence`, `resonance`, `tension`, `shadow_depth` (each ∈ [0, 1]). |
| `CognitivePayload` | `core/context_engine.py` | Structured turn payload. Distinct fields for `user_input`, `internal_log`, `response`, and a free-form `metadata` dict — so pipeline steps don't fight over a single string slot. |
| `Context[A]` | `core/context_engine.py` | Immutable container: `state`, `history: list[CognitiveState]`, and a `value: A`. |
| `ContextWorker[A]` | `core/context_engine.py` | The comonadic wrapper. Exposes `current()`, `state`, `history`, `extend()`, `fork()`, `merge()`. |

`ContextWorker.extend(op)` is the only mutation-shaped API. It:

1. Calls `op(self)`.
2. If the op returns `(payload, new_state)` tuple → uses the new state; otherwise keeps the old state.
3. Appends the *previous* state to `history` and constructs a fresh `Context` /
   `ContextWorker` for the next step. The original worker is never mutated.

`fork(ops)` returns one `ContextWorker` per operation, all starting from the
same root context. `merge(branches, selector)` collapses them back into a
single lineage via a caller-supplied selector.

---

## Built-in operations (`core/cognitive_ops.py`)

| Op | Reads | Writes | Notes |
|----|-------|--------|-------|
| `pedi_regulation_step` | `state.tension`, `state.shadow_depth` | New state with dampened extremes, `payload.internal_log` | Tension > 0.6 → −0.2 tension and −0.1 coherence. Shadow depth > 0.7 → +0.3 tension. Bounds re-clamped to [0, 1]. |
| `state_conditioned_llm` | Current state | `payload.response` | The "Affective Logic Gate" — selects a mode/prompt directive (Strict Logical, Exploratory Intuitive, Shadow-Driven Projection, Standard Empathic) for the downstream LLM. Does **not** call the LLM itself; it returns the *prompt directive* the LLM should follow. |
| `predicted_transition_step(predictor)` | Current state | Stores `payload.metadata["predicted_state"]` | Diagnostic step. Runs `predictor(state)`, stashes the predicted next state, then returns the *actual* state unchanged so the real pipeline continues. Used by `TransitionComparator` for predictor evaluation. |

All three ops are pure functions over a `ContextWorker[CognitivePayload]`. They
never read or mutate `global_workspace`, `svalbard_vault`, or other singletons
— that side-effecting work happens after the pipeline produces its final state.

---

## CLI integration: the `--comonadic` flag

`interfaces/main.py` runs the standard fly-by-wire path by default (see
[FALSIFIABILITY.md](FALSIFIABILITY.md) and `GlobalWorkspace.execute_cli_cycle`).
Passing `--comonadic` on the CLI swaps in the bridge path for that turn:

```bash
python interfaces/main.py --comonadic
```

For each user message it:

1. Builds a `CognitiveState` from the current `raw_active_state` (coherence /
   resonance / tension / shadow_depth).
2. Wraps it in a `Context[CognitivePayload]` with the user message.
3. Extends the pipeline with `pedi_regulation_step` → `state_conditioned_llm`.
4. Pushes the worker's final state back into the physics and shadow
   singletons (`_physics.state.{resonance,tension}` and `_shadow._state.depth`)
   so the rest of the system sees the regulated values.
5. Assembles the regular orchestrator prompt and prepends the gate's directive
   (`[System Direction: …]`) before calling `brain.agent_turn`.
6. Logs the per-dimension state diff via
   `interfaces/comonad_cli.calculate_state_diff` and the worker's `history`.

### Sealing path protection

After the pipeline finishes, `main.py` re-runs `_workspace.pedi.evaluate_cycle`
on `final_state.model_dump()` to read the regulator's verdict. The Svalbard
core-memory deposit is guarded by:

```python
is_hold_state = status.startswith("HOLD")
in_correcting_state = (status == "CORRECTING")
if not is_hold_state and not in_correcting_state:
    _workspace.vault.deposit_core_memory(..., quarantined=(shadow_depth > 0.75))
```

So a comonadic turn can only seal an `IdentityBlock` when PEDI returns
`STABLE` or `EVOLVING`. `HOLD_*` (anchor not yet trustworthy) and `CORRECTING`
(state being pulled back) both suppress the deposit. This is the same
invariant `execute_cli_cycle` enforces for the default path — see
[VAULT_STABILITY_NOTES.md](VAULT_STABILITY_NOTES.md) for the underlying status
table.

---

## When to use which path

| Need | Path |
|------|------|
| Normal interactive turn | Default (`execute_cli_cycle`) — full plugin loop, workspace competition, Lantern-4 veto |
| Reasoning about regulated state without touching singletons | `--comonadic`, or call the ops directly from a test |
| Branch & compare candidate responses | `worker.fork([op_a, op_b])` then `worker.merge(branches, selector)` |
| Evaluate a state predictor against the real trajectory | Insert `predicted_transition_step(predictor)` and read `payload.metadata["predicted_state"]` after the pipeline |

The two paths share the same `CognitiveState` semantics and the same vault
sealing invariants. The bridge is additive — disabling it leaves all existing
behavior intact.

---

## Quick reference: a minimal cycle

```python
from drift.core.context_engine import (
    CognitiveState, CognitivePayload, Context, ContextWorker,
)
from drift.core.cognitive_ops import pedi_regulation_step, state_conditioned_llm

state = CognitiveState(coherence=0.8, resonance=0.5, tension=0.8, shadow_depth=0.2)
payload = CognitivePayload(user_input="Why did you disagree with me yesterday?")
worker = ContextWorker[CognitivePayload](Context(state=state, value=payload))

worker = worker.extend(pedi_regulation_step)
worker = worker.extend(state_conditioned_llm)

print(worker.current().internal_log)   # what PEDI did
print(worker.current().response)       # gate directive for the LLM
print(worker.history[0], worker.state) # initial vs final state
```

`interfaces/comonad_cli.py` contains a runnable version of the same flow plus
a `calculate_state_diff` helper used by `main.py --comonadic`.
