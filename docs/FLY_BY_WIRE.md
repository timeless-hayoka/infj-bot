# PEDI Fly-By-Wire CLI Cycle

The CLI loop in `interfaces/main.py` does not call the LLM directly anymore. Each user turn is routed through `GlobalWorkspace.execute_cli_cycle(...)`, which **regulates the bot's internal state vector before the prompt is built** and then optionally **seals the exchange into a long‑term vault** after the model replies.

This page describes the contract, the four phases of one cycle, and the optional companion modules (`SvalbardVault`, `PEDIEngine`) that the workspace expects to find.

For background on PEDI as a metric, see [DMU_PEDI_TEST_PLAN.md](DMU_PEDI_TEST_PLAN.md). For why the regulator is wired into the workspace at all, see [HOW_INFJ_BOT_WORKS.md](HOW_INFJ_BOT_WORKS.md).

---

## 1. Why this wrapper exists

A normal turn would be:

```
build_chat_prompt → brain.agent_turn → save_interaction
```

But several subsystems (`PhysicsEngine`, `Shadow`, the Elysium council) carry mutable state that drifts every tick. If the user’s message arrives mid-drift — for example, while `resonance` is spiking from a previous turn — the prompt assembled in that moment captures a transient outlier, not the bot's "true" current condition. PEDI's job is to **smooth those raw values into a regulated vector** before they ever touch the prompt builder, the same way a fly-by-wire flight computer translates noisy stick inputs into stable control surface commands.

The four-component vector the regulator works on is:

| Key | Sourced from | Default |
|------|--------------|---------|
| `resonance` | `PhysicsEngine.get_state()["resonance"]` | `0.8` |
| `tension` | `PhysicsEngine.get_state()["tension"]` | `0.2` |
| `shadow_depth` | `Shadow.get_state().depth` | `0.2` |
| `coherence` | `Elysium.council_status()["nexus"]["coherence_score"]` | `0.8` |

Each source is wrapped in `try/except`; any failure falls back to the default so a missing subsystem cannot stall the chat loop.

---

## 2. The cycle, phase by phase

```python
output, regulated_state, status = await asyncio.to_thread(
    _workspace.execute_cli_cycle,
    raw_active_state,
    user_input,
    generate_response_func,
)
```

`execute_cli_cycle` implements four phases:

### Phase 1 — PEDI regulation (pre‑think)

```python
regulated_state, correction, status = self.pedi.evaluate_cycle(raw_active_state)
```

`PEDIEngine.evaluate_cycle` returns:

- `regulated_state` — the four-component dict after smoothing.
- `correction` — opaque diagnostic payload (logged, not consumed).
- `status` — `"STABLE"`, `"EVOLVING"`, or any other tag the engine emits. Anything other than `STABLE` is surfaced as `[*] PEDI Fly-By-Wire status: <status>` in the CLI.

### Phase 2 — bound generation

The CLI builds a `generate_response_func(user_input, regulated_state)` closure. The closure:

1. Writes the regulated `resonance` / `tension` back into the live `PhysicsEngine` and persists.
2. Writes the regulated `shadow_depth` into the live `Shadow` and persists.
3. Calls `cognitive_orchestrator.assemble_prompt(...)` — so the prompt is built **after** the regulated values have replaced the raw ones.
4. Calls `brain.agent_turn(prompt, tools_enabled=True)`.
5. Stashes `prompt`, `emotion`, `dissonance` onto the function object itself (`generate_response_func.prompt = ...`) so the caller can retrieve them without restructuring the return shape.

### Phase 3 — Lantern-4 veto (post‑think)

Only runs when `status == "EVOLVING"` or `regulated_state["resonance"] > 0.90`. The check is implemented in `GlobalWorkspace._lantern_4_veto`:

| Criterion | Rule | Action |
|-----------|------|--------|
| C1: resonance floor | `resonance < 0.85` | `(approved=False, quarantine=False)` — reject |
| C2: semantic density | `0.85 ≤ resonance < 0.95` **and** (`len(user_input.split()) < 5` **or** `len(sys_response.split()) < 10`) | reject; logs `[LANTERN-4] Rejected: Exchange lacks semantic depth.` |
| C2 override | `resonance ≥ 0.95` | length check skipped — "absolute fire" exchanges are always eligible |
| C3: shadow quarantine | `shadow_depth > 0.75` | `(approved=True, quarantine=True)` — accept, but flag for PEDI not to anchor on it |
| Otherwise | passes all gates | `(approved=True, quarantine=False)` |

### Phase 4 — Svalbard sealing

If `approved`, `self.vault.deposit_core_memory(...)` writes the exchange to the long-term vault with these named fields:

```python
self.vault.deposit_core_memory(
    event=f"CLI Milestone: {user_input[:40]}...",
    user_q=user_input,
    sys_q=sys_response,
    current_state=regulated_state,
    quarantined=quarantine,
)
```

`current_state` is the **regulated** vector, not the raw one — anything anchored in Svalbard reflects the bot's smoothed inner condition at the moment of the milestone, not the noise that triggered the turn.

Finally the regulated state is returned to the CLI so the next turn’s raw snapshot can be compared against it.

---

## 3. Companion modules — `SvalbardVault` and `PEDIEngine`

`global_workspace.py` imports them with a soft path‑fallback:

```python
try:
    from infj_bot.core.svalbard_vault import SvalbardVault
    from infj_bot.core.pedi_metrics import PEDIEngine
except ImportError:
    from svalbard_vault import SvalbardVault
    from pedi_metrics import PEDIEngine
```

These modules are **not vendored in this repository**. They are expected to live alongside `core/` (preferred), or on `sys.path` as top-level modules. If neither location resolves, `GlobalWorkspace()` raises `ImportError` at construction — which means `get_workspace()` raises on first call, which means the CLI never starts.

The contracts the workspace relies on (verified against `core/global_workspace.py`):

### `SvalbardVault`
- `verify_identity_integrity(full_chain: bool) -> Any` — called once in `__init__` with `full_chain=False`. Return value is ignored; raising is fatal.
- `deposit_core_memory(event: str, user_q: str, sys_q: str, current_state: dict, quarantined: bool) -> Any` — must accept all five keyword args.

### `PEDIEngine`
- `PEDIEngine(vault)` — constructor takes the Svalbard instance.
- `evaluate_cycle(raw_active_state: dict) -> tuple[dict, Any, str]` — returns `(regulated_state, correction, status)`.

`GlobalWorkspace._self_check_diagnostics` calls `sys.exit(1)` if either object is falsy at construction. There is no graceful degradation path — the workspace is "Fly-By-Wire all the way down or nothing." If you want a build without PEDI, stub the two modules with no-op implementations that return their inputs unchanged and status `"STABLE"`.

> The PEDI metric implementation that ships in this repo lives at `metrics/pedi.py` and operates on the 7-axis homeostatic vector (see [DMU_PEDI_TEST_PLAN.md](DMU_PEDI_TEST_PLAN.md)). The `PEDIEngine` referenced above is a different surface — it works on the 4-axis fly-by-wire vector and returns a `(state, correction, status)` triple. They are complementary, not the same class.

---

## 4. What the web app does instead

The CLI is the only surface that calls `execute_cli_cycle`. The Flask/SocketIO web app in `interfaces/web_app.py` goes through `chat_reply(message, session_res)`, which builds the prompt directly from the session-scoped state and skips the regulator. If you need fly-by-wire behavior in the web UI, wrap `chat_reply` the same way `chat_loop` wraps the CLI: extract a raw vector from the per-session subsystems, hand it to `_workspace.execute_cli_cycle`, and write the result back to `session_res.memory` / `session_res.history`.

See [WEB_APP_SESSIONS.md](WEB_APP_SESSIONS.md) for the session lifecycle and why singleton subsystems make a direct port non-trivial today.

---

## 5. Operational notes

- **Off-thread.** The CLI calls `execute_cli_cycle` via `asyncio.to_thread` so the workspace's blocking PEDI / vault I/O does not stall the event loop.
- **Status logging.** Only `status != "STABLE"` is printed; STABLE turns are silent. Watch stdout for `[LANTERN-4]` and `[SYSTEM]` markers for the rest of the trace.
- **Default fallback vector.** If every sensor read fails, the raw state is `{coherence: 0.8, resonance: 0.8, tension: 0.2, shadow_depth: 0.2}`. PEDI will regulate it to roughly itself and `status` will be `STABLE` — the cycle still runs.
- **Closure trick.** `generate_response_func.prompt = ...` is intentional: the CLI needs the prompt/emotion/dissonance for `brain.evaluate_last(...)` and `memory.save_interaction(...)` *after* `execute_cli_cycle` returns. Treat the function attributes as a stable contract.
