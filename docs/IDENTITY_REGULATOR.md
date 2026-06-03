# Identity Regulator — PEDI v2.2 & Lantern-4

> Code: `core/pedi_metrics.py`, `core/svalbard_vault.py`,
> `core/global_workspace.py` (`execute_cli_cycle`, `_lantern_4_veto`).
> Related runtime docs: [VAULT_STABILITY_NOTES.md](VAULT_STABILITY_NOTES.md)
> (older), [COMONADIC_BRIDGE.md](COMONADIC_BRIDGE.md).

This document covers the **production** identity regulator that runs on every
chat turn: how the PEDI engine pulls an anchor from the Svalbard ledger, how it
decides between holding / correcting / evolving / sealing the current state,
and how the Lantern-4 veto gates writes to the immutable ledger.

> The `metrics/pedi.py` module in this repo is a separate, unrelated
> implementation that measures state fluidity across context-window resets.
> Do not confuse the two — see [DMU_PEDI_TEST_PLAN.md](DMU_PEDI_TEST_PLAN.md)
> for disambiguation.

---

## At a glance

```
raw_active_state  ──►  PEDIEngine.evaluate_cycle  ──►  regulated_state, status
                         │
                         ├─ STABLE          : pass through, no correction
                         ├─ CORRECTING      : pull state toward identity anchor
                         ├─ EVOLVING        : high drift but improving — allow
                         └─ HOLD_<reason>   : freeze state; ledger not usable

regulated_state   ──►  generate_response_func (LLM)
sys_response      ──►  Lantern-4 veto (status, resonance, length, shadow_depth)
                         │
                         └─ approved + not HOLD/CORRECTING ──► SvalbardVault.deposit_core_memory
```

Wired in `GlobalWorkspace.execute_cli_cycle(raw_active_state, user_input, generate_response_func)`.

---

## Constants (single source of truth: `core/pedi_metrics.py`)

| Name                | Value                                       | Meaning                                              |
|---------------------|---------------------------------------------|------------------------------------------------------|
| `DIMS`              | `("coherence", "resonance", "tension")`     | Dimensions used for anchor distance math.            |
| `NORM`              | `1.5`                                       | Denominator that normalises `sqrt(Σ Δ²)` to `[0, 1]`.|
| `MIN_USABLE_BLOCKS` | `3`                                         | Cold-start threshold for trusting the ledger anchor. |
| `FALLBACK_ANCHOR`   | `{coherence: 0.85, resonance: 0.82, tension: 0.12}` | Static anchor used during HOLD states.        |

`shadow_depth` is stored on the ledger but **intentionally excluded** from the
anchor distance calculation. The docstring in `core/pedi_metrics.py` records
this decision: keeping anchor math 3-dimensional aligns with the paper's state
space model.

---

## `AnchorResult` — explicit cold-start / failure signalling

`_get_identity_center_of_gravity()` now returns an `AnchorResult` dataclass
instead of `Optional[dict]`:

```python
@dataclass
class AnchorResult:
    anchor: Dict[str, float]   # always populated (real or FALLBACK_ANCHOR)
    valid: bool                # False ⇒ caller MUST treat as cold-start / hold
    reason: str                # "ok" | "no_vault" | "no_blocks" | "cold_start"
                               # | "read_error: <msg>"
```

The engine derives the live anchor as follows:

1. Read the last **20** non-empty lines of `svalbard_ledger.jsonl`.
2. Drop blocks that are `quarantined: true` or **degenerate** (`coherence` and
   `resonance` both `< 1e-6` — a sign of an empty / zeroed write).
3. If fewer than `MIN_USABLE_BLOCKS` survive → return
   `AnchorResult(FALLBACK_ANCHOR, valid=False, reason="cold_start")`.
4. Otherwise, take a **resonance × coherence**-weighted mean over `DIMS`
   (weight floor `0.1`). If every weight is below the floor, fall back to a
   plain mean of the same blocks.

This guarantees the engine never crashes on a missing or corrupt ledger; it
hands back the static `FALLBACK_ANCHOR` and a `HOLD_*` status so the caller
can adjust behaviour rather than silently anchor to garbage.

---

## `evaluate_cycle(raw_active_state)` — the regulation loop

Returns `(regulated_state, applied_correction, status)`.

The status string is the contract callers depend on. Possible values:

| Status                | When                                                                              |
|-----------------------|-----------------------------------------------------------------------------------|
| `HOLD_NO_VAULT`       | The vault object is missing or has no `latest_hash` attribute.                    |
| `HOLD_NO_BLOCKS`      | Ledger file is empty or unreadable in a benign way.                               |
| `HOLD_COLD_START`     | Fewer than `MIN_USABLE_BLOCKS` usable blocks after quarantine/degeneracy filter.  |
| `HOLD_READ_ERROR`     | Exception raised while reading the ledger (message kept in `AnchorResult.reason`).|
| `EVOLVING`            | `instant_drift > 0.28` **and** `improvement_score > 0.05` — drift in the right direction.|
| `CORRECTING`          | `applied_correction > 0.05` after the smoothing + windup logic below.             |
| `STABLE`              | Otherwise (no meaningful correction needed).                                      |

### Hold semantics

When `AnchorResult.valid` is `False` the engine:

- Initialises `self.perceived_state` from `raw_active_state` if it is still `None`.
- **Copies any new keys** from `raw_active_state` (so callers can observe new
  signals) but does *not* apply perception smoothing or correction.
- Returns the current `perceived_state` with `applied_correction = 0.0` and
  status `HOLD_<REASON>`.

Hold states are the signal that the regulator cannot trust the ledger this turn
— callers must **not** seal new blocks based on a held state (see Lantern-4).

### Smoothing, drift, and correction

When `AnchorResult.valid` is `True`:

```
# 1. Perception smoothing (only the 3 DIMS)
perceived[k] = perceived[k] * 0.4 + raw_active[k] * 0.6

# 2. Distance to anchor
instant_drift = min(1.0, sqrt(Σ_{k in DIMS} (perceived[k] - anchor[k])²) / NORM)

# 3. Improvement score (signed)
improvement = 0.5·Δcoherence + 0.4·Δresonance − 0.1·Δtension

# 4. Decay the meta-drift accumulator each turn
meta_drift *= 0.98

# 5. Evolution gate (escape valve)
if instant_drift > 0.28 and improvement > 0.05:
    meta_drift *= 0.3
    return EVOLVING

# 6. Otherwise accumulate
meta_drift = min(meta_drift + 0.1·instant_drift, 1.0)
total_pressure   = instant_drift + meta_drift
raw_correction   = min(0.85, total_pressure²)
applied          = raw_correction * 0.22         # smooth reaction weight

if applied > 0.05:
    perceived[k] = perceived[k]·(1-applied) + anchor[k]·applied   # for k in DIMS
    meta_drift  *= 0.7
    return CORRECTING

return STABLE
```

Non-`DIMS` keys present on `raw_active_state` (e.g. `shadow_depth`) flow
through unchanged.

---

## Svalbard ledger — what a block looks like

`core/svalbard_vault.py` defines `IdentityBlock`:

```jsonc
{
  "version": "2.0",
  "timestamp": "...",
  "event_summary": "CLI Milestone: ...",
  "user_quote": "...",
  "system_quote": "...",
  "emotional_state": {
    "coherence": 0.92, "resonance": 0.96, "tension": 0.10, "shadow_depth": 0.18
  },
  "quarantined": false,
  "prior_hash": "<sha256 of previous block>",
  "block_hash": "<sha256 of this block>"
}
```

The vault path defaults to `<DATA_ROOT>/svalbard_ledger.jsonl` and can be
overridden with `DRIFT_VAULT_PATH`. The HMAC secret comes from
`DRIFT_VAULT_SECRET` — the dev default is intentionally insecure and emits a
warning on startup. Set it before any production-like run.

---

## Lantern-4 veto

`GlobalWorkspace._lantern_4_veto(user_input, sys_response, active_state)` is
the gate between PEDI and the ledger. It returns `(approved, quarantine)`:

| Check                                                                  | Effect                          |
|------------------------------------------------------------------------|---------------------------------|
| `resonance < 0.85`                                                     | Rejected — not significant.     |
| `0.85 ≤ resonance < 0.95` **and** (user words `< 5` or sys words `<10`)| Rejected — lacks semantic depth.|
| `resonance ≥ 0.95`                                                     | Length checks bypassed.         |
| `shadow_depth > 0.75`                                                  | Approved but `quarantine=True`. |

`execute_cli_cycle` only consults Lantern-4 when the PEDI status is `EVOLVING`
or the regulated state's resonance crosses `0.90`, and it **never** seals when
status is a `HOLD_*` or `CORRECTING` — the regulator cannot certify a clean
anchor in those cases.

The `--comonadic` chat loop applies the same hold/correcting guard before
calling `vault.deposit_core_memory(...)`; see [COMONADIC_BRIDGE.md](COMONADIC_BRIDGE.md).

---

## End-to-end sequence (default CLI path)

```
chat_loop() ──► raw_active_state from physics + shadow + elysium
            └─► execute_cli_cycle(raw_active_state, user_input, gen_fn)
                 ├─ pedi.evaluate_cycle(raw_active_state) → regulated, status
                 ├─ gen_fn(user_input, regulated)            (LLM call)
                 ├─ if status == EVOLVING or regulated.resonance > 0.90
                 │     and status not in {HOLD_*, CORRECTING}:
                 │       approved, quarantine = _lantern_4_veto(...)
                 │       if approved:
                 │           vault.deposit_core_memory(..., quarantined=quarantine)
                 └─ return sys_response, regulated, status
```

If `status != "STABLE"` the CLI prints
`[*] PEDI Fly-By-Wire status: <status>` so the operator can see when the
regulator intervened.

---

## Operational checks

Use these when triaging "the bot feels off":

1. **Is the ledger growing?** `wc -l "$DRIFT_VAULT_PATH"` after a known
   high-resonance exchange. If it isn't, the most likely cause is
   `status in {HOLD_*, CORRECTING}` blocking the seal — check the printed
   Fly-By-Wire status, then `_get_identity_center_of_gravity().reason`.
2. **Is the engine in cold-start?** The ledger needs at least
   `MIN_USABLE_BLOCKS = 3` non-quarantined, non-degenerate blocks before the
   real anchor is used.
3. **Is the secret set?** Without `DRIFT_VAULT_SECRET` the HMAC chain runs on a
   default secret and stdout warns at boot. Treat any production deployment
   without this variable as broken.
4. **Did Lantern-4 reject?** It logs `[LANTERN-4] Rejected: ...` and
   `[LANTERN-4] Nomination approved.` lines to stdout — grep those before
   second-guessing PEDI math.
