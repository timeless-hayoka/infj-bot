# Vault / PEDI Stability Notes

*Saved 2026-05-28 — updated 2026-06-05 — covers `core/svalbard_vault.py` + `core/pedi_metrics.py`*

---

## What was added

**SvalbardVault** — tamper-evident JSONL ledger. Every significant exchange gets sealed as a
cryptographically chained `IdentityBlock` (SHA-256 hash chain + HMAC signature). DRIFT's
long-term episodic identity memory — immutable, verifiable, weighted by emotional
resonance/coherence.

**PEDIEngine** (Persistence-Embodiment-Drift Index, `core/pedi_metrics.py`) — reads the last
20 vault blocks as DRIFT's "center of gravity" and uses it to regulate the active emotional
state in real-time. Each cycle returns one of these statuses (see `PEDIEngine.evaluate_cycle`):

| Status | When it fires | Effect on state |
|--------|---------------|-----------------|
| `STABLE` | Perceived state already inside the corrective deadband (`applied_correction ≤ 0.05`) | Passes perceived state through unchanged |
| `CORRECTING` | Drift exceeds the deadband; meta-drift accumulator has built up | Blends perceived state toward anchor with `applied_correction` and decays the accumulator by 0.7× |
| `EVOLVING` | `instant_drift > 0.28` *and* `improvement_score > 0.05` — the bot is drifting but in a healthier direction | Skips correction, decays accumulator aggressively (0.3×) |
| `HOLD_*` | The anchor itself is not yet trustworthy. Suffix names the reason: `NO_VAULT`, `NO_BLOCKS`, `COLD_START` (fewer than `MIN_USABLE_BLOCKS = 3` usable blocks), `READ_ERROR` | Returns the most recent perceived state with `correction = 0.0`; sealing path is suppressed by callers (see `interfaces/main.py`) |

The 3D state space the index operates on is `DIMS = ("coherence", "resonance", "tension")`
with a global normalizer `NORM = 1.5`. `shadow_depth` is intentionally **not** in `DIMS` —
it is tracked on each `IdentityBlock` and used for quarantine decisions, but excluded from
anchor distance to keep the math aligned with the paper's 3D state-space model (see the
top-of-file comment in `core/pedi_metrics.py`). The fallback anchor used during cold start
is `{coherence: 0.85, resonance: 0.82, tension: 0.12}`.

**GlobalWorkspace integration** — `execute_cli_cycle()` wires everything together: state is
regulated by PEDI before generation, and high-resonance moments (> 0.85) are sealed to the
vault via the **Lantern-4 veto**. Shadow depth > 0.75 marks blocks as quarantined.
**Sealing is suppressed when status starts with `HOLD_` or equals `CORRECTING`** — only
`STABLE` or `EVOLVING` cycles can deposit a new core memory. This prevents the anchor from
locking onto cold-start defaults or chasing its own corrections.

---

## How to know it's stable

Three things tell you a system is stable:

### 1. Tests that can fail

Zero tests currently cover vault or PEDI. If the hash chain breaks, the HMAC silently
mismatches, or PEDI starts over-correcting state, you won't know until DRIFT is acting weird
in a real conversation.

**Need:** `tests/test_vault.py` covering:
- Vault writes a block and the hash chain verifies
- Tampered block fails integrity check
- PEDI `STABLE` / `CORRECTING` / `EVOLVING` / `HOLD_*` all trigger under the right conditions
- Vault degrades gracefully when ledger is missing or corrupt

### 2. Observable output you can inspect

The vault writes to `svalbard_ledger.jsonl`. No command currently exposes vault/PEDI status
from within the bot.

**Need:** A `/vault status` or `/pedi status` command showing:
- Last sealed block hash + timestamp
- Current PEDI status (STABLE / CORRECTING / EVOLVING / HOLD_*)
- Correction pressure + meta-drift accumulator value
- Integrity check result

### 3. The `sys.exit(1)` problem

In `global_workspace.py → _self_check_diagnostics()`, if `SvalbardVault()` or `PEDIEngine()`
fail to initialize (missing directory, bad permissions, corrupt ledger), the whole bot dies
instantly with no recovery.

**Need:** Graceful degraded mode — vault disabled, PEDI passes state through unchanged —
so the bot can still run if the persistence layer has an issue.

---

## Action items (priority order)

1. Write `tests/test_vault.py` (vault + PEDI unit tests)
2. Replace `sys.exit(1)` in `_self_check_diagnostics` with degraded-mode fallback
3. Add `/vault status` slash command
4. Set `DRIFT_VAULT_SECRET` in `.env` (currently uses insecure default)
