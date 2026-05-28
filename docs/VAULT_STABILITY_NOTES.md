# Vault / PEDI Stability Notes

*Saved 2026-05-28 — covers `core/svalbard_vault.py` + `core/pedi_metrics.py`*

---

## What was added

**SvalbardVault** — tamper-evident JSONL ledger. Every significant exchange gets sealed as a
cryptographically chained `IdentityBlock` (SHA-256 hash chain + HMAC signature). DRIFT's
long-term episodic identity memory — immutable, verifiable, weighted by emotional
resonance/coherence.

**PEDIEngine** (Persistence-Embodiment-Drift Index) — reads the last 20 vault blocks as
DRIFT's "center of gravity" and uses it to regulate the active emotional state in real-time.
Three outcomes per cycle:

| Status | Meaning |
|--------|---------|
| `STABLE` | No correction needed |
| `CORRECTING` | Pulls state back toward identity anchor |
| `EVOLVING` | High-drift but improving — let it run |

**GlobalWorkspace integration** — `execute_cli_cycle()` wires everything together: state is
regulated by PEDI before generation, and high-resonance moments (> 0.85) are sealed to the
vault via the **Lantern-4 veto**. Shadow depth > 0.75 marks blocks as quarantined.

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
- PEDI `STABLE` / `CORRECTING` / `EVOLVING` all trigger under the right conditions
- Vault degrades gracefully when ledger is missing or corrupt

### 2. Observable output you can inspect

The vault writes to `svalbard_ledger.jsonl`. No command currently exposes vault/PEDI status
from within the bot.

**Need:** A `/vault status` or `/pedi status` command showing:
- Last sealed block hash + timestamp
- Current PEDI status (STABLE / CORRECTING / EVOLVING)
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
