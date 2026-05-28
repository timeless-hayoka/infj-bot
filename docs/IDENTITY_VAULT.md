# Identity Vault & PEDI Engine

DRIFT distinguishes between **conversational memory** (Chroma + `history.jsonl`
+ subsystem SQLite stores) and **identity memory** — a much smaller, hash-chained
ledger of the moments that should anchor *who the bot is* across resets,
forks, and restorations.

This document describes the two modules that implement identity memory:

| Module | Role |
|---|---|
| `core/svalbard_vault.py` | Append-only, hash-chained, HMAC-signed ledger of high-salience "core" memories. |
| `core/pedi_metrics.py` | **PEDI Engine** — a fly-by-wire identity regulator that smooths the active cognitive state toward the gravity center of recent vault blocks. |

Both modules are wired into `GlobalWorkspace.__init__` (`core/global_workspace.py`)
and run on the conscious workspace cycle, so every chat turn passes through
them when the workspace is live.

---

## 1. A note on the name "PEDI"

There are **two distinct PEDI implementations** in this repository, and they
measure different things. Do not confuse them:

| Module | Acronym | Measures | Storage |
|---|---|---|---|
| `metrics/pedi.py` | **P**erformance and **E**fficiency **D**etection **I**ndex | Continuity of the 7-dimensional **homeostatic** state vector across context-window resets (state fluidity). | SQLite (`pedi.db`). |
| `core/pedi_metrics.py` | **P**ersistence–**E**mbodiment–**D**rift **I**ndex | Distance of the current 4-dimensional **emotional/identity** state (`coherence`, `tension`, `resonance`, `shadow_depth`) from the weighted gravity center of recent Svalbard blocks. | In-memory accumulator; reads the Svalbard JSONL. |

When this document says "PEDI" without a qualifier, it means
`core/pedi_metrics.py` — the identity regulator. See
[`DMU_PEDI_TEST_PLAN.md`](DMU_PEDI_TEST_PLAN.md) for the homeostatic
fluidity PEDI in `metrics/pedi.py`.

---

## 2. Svalbard Vault (`core/svalbard_vault.py`)

> Named after the Svalbard Global Seed Vault: the idea is a small, durable,
> tamper-evident store of seed memories the bot can rebuild identity from.

### 2.1 What goes in it

Not every turn. Only **high-resonance milestones** approved by the Lantern-4
gate in `GlobalWorkspace` (see §4). A single entry is an `IdentityBlock`:

```python
@dataclass
class IdentityBlock:
    timestamp: str              # ISO-8601 UTC
    event_summary: str          # e.g. "CLI Milestone: <user prefix>…"
    user_quote: str             # raw user input that triggered the block
    system_quote: str           # the response DRIFT produced
    emotional_state: EmotionalAnchor  # see below
    prior_hash: str             # block_hash of the previous entry
    quarantined: bool = False   # set when shadow_depth is high (§4)
    version: str = "2.0"
    block_hash: str = ""        # sha256(canonical-json payload)
```

`EmotionalAnchor` holds the four-axis snapshot:

```python
@dataclass
class EmotionalAnchor:
    coherence: float    # internal consistency / clarity
    tension: float      # internal friction
    resonance: float    # depth of contact with the user
    shadow_depth: float # how much unintegrated material is active
```

### 2.2 On-disk layout

Two files, paths controlled by environment variables:

| Path | Purpose | Env var |
|---|---|---|
| `<VAULT_PATH>` | Append-only JSONL of `IdentityBlock` records. | `DRIFT_VAULT_PATH` |
| `<VAULT_PATH>.sig` | Hex HMAC-SHA256 of the latest `block_hash`, signed with `DRIFT_VAULT_SECRET`. | `DRIFT_VAULT_SECRET` |

Resolution order in `svalbard_vault.py`:

1. `DRIFT_VAULT_PATH` env var if set.
2. Otherwise `<DATA_ROOT>/svalbard_ledger.jsonl` from
   `infj_bot.core.config.DATA_ROOT`.
3. Otherwise `~/.drift_os/svalbard_ledger.jsonl` (legacy fallback).

The signature file is always `<VAULT_PATH>.sig`. The vault directory is
created automatically by `self_check_diagnostics()` if missing.

### 2.3 Integrity model

- **Hash chain.** Every block stores `prior_hash` (the previous block's
  `block_hash`) and its own `block_hash = sha256(canonical_payload)`. The
  canonical payload is `json.dumps(...)` with `sort_keys=True` and tight
  separators so any byte-level mutation breaks the chain.
- **HMAC root signature.** After each append, `_sign_root_hash()` writes
  `HMAC-SHA256(DRIFT_VAULT_SECRET, latest_hash)` to `<VAULT_PATH>.sig`. A
  process that can read the ledger but doesn't hold the secret cannot forge a
  matching signature for a tampered chain.
- **Verification.** `verify_identity_integrity(full_chain=False)` runs at
  workspace startup and only checks the signature; pass `full_chain=True` to
  walk the entire JSONL, re-derive each `block_hash`, and verify continuity.
- **Durability.** Both writes (`_sign_root_hash` and `deposit_core_memory`)
  call `os.fsync()` after `flush()`. The module flags this as a known
  bottleneck — if you push high-throughput workloads, route writes through an
  async queue (TODOs are already noted in the source).

### 2.4 `DRIFT_VAULT_SECRET`

If the secret is unset, `self_check_diagnostics()` prints a warning and uses
`"default_dev_secret_do_not_use_in_prod"`. In any deployment that matters,
set `DRIFT_VAULT_SECRET` to a long random value and **back up the secret
separately from the vault file** — losing the secret means you can no longer
verify the ledger, and rotating it requires re-signing only the latest hash
(the chain itself is hash-based and unaffected).

### 2.5 Public API surface

```python
vault = SvalbardVault()                                  # __init__ runs self-check + loads latest_hash
vault.verify_identity_integrity(full_chain=False)         # signature only
vault.verify_identity_integrity(full_chain=True)          # signature + full chain replay
vault.deposit_core_memory(
    event="CLI Milestone: …",
    user_q="…",
    sys_q="…",
    current_state={"coherence": 0.82, "tension": 0.12,
                   "resonance": 0.94, "shadow_depth": 0.31},
    quarantined=False,
)
vault.latest_hash    # str, "0"*64 if the ledger is empty
```

Stdout prints prefixed with `[VAULT]`, `[QUARANTINED VAULT]`,
`[CRITICAL SECURITY FAILURE]`, or `[CRITICAL ERROR]` are the operator-visible
signal that something happened — there is no separate logger today.

---

## 3. PEDI Engine (`core/pedi_metrics.py`)

The vault stores what *was* true; PEDI keeps the bot's *current* affective
state from drifting too far from it. It is a feedback regulator — what the
workspace calls "fly-by-wire" — not a memory store.

### 3.1 Inputs and outputs

```python
engine = PEDIEngine(vault_instance=SvalbardVault())
regulated_state, correction, status = engine.evaluate_cycle(raw_active_state)
```

- `raw_active_state` — dict with at least `coherence`, `tension`, `resonance`,
  `shadow_depth`. Defaults to `0.5` for any missing axis.
- `regulated_state` — same shape, possibly nudged toward the gravity center.
- `correction` — float in `[0, 0.85]`; how much pull was applied this cycle
  (`0.0` means no nudge).
- `status` — one of:
  - `"NO_ANCHOR"` — vault empty / unreadable; nothing to anchor to.
  - `"EVOLVING"` — drift is large *and* moving in a healthy direction
    (improvement_score above threshold); the engine accepts the new state
    and decays meta-drift instead of pulling back.
  - `"CORRECTING"` — meta-drift accumulated past tolerance; the engine
    pulled the perceived state toward the anchor.
  - `"STABLE"` — within tolerance; no action.

### 3.2 Algorithm at a glance

1. **Gravity center** — `_get_identity_center_of_gravity()` reads the last
   ~20 lines of `<VAULT_PATH>`, skips `quarantined` blocks, and computes a
   resonance×coherence-weighted average of the four axes.
2. **Perception smoothing** — the perceived state is a 0.6-weighted EMA over
   the raw active state, so single noisy turns can't whipsaw identity.
3. **Drift measurement** — Euclidean distance (capped at 1.0) between
   perceived state and the anchor.
4. **Evolution gate** — at `instant_drift > 0.28` and
   `improvement_score > 0.05` (coherence/resonance up, tension down), the
   engine treats the move as healthy growth, decays the meta-drift
   accumulator, and returns `EVOLVING`.
5. **Otherwise**, meta-drift accumulates (`+= 0.1 * instant_drift`, capped at
   `1.0`, with a per-cycle decay of `0.98` to prevent integral windup).
6. **Correction** — `raw_correction_weight = min(0.85, total_pressure**2)`,
   smoothed by a `reaction_weight = 0.22` factor. If the applied correction
   exceeds `0.05`, perceived state is mixed with the anchor by that weight
   and the accumulator is dampened (`*= 0.7`).

Tuning constants (`0.28`, `0.22`, `0.6`, `0.98`, `0.7`) are tagged "V2.2
Tuned" in the source. Treat them as hot-path knobs — changing them changes
how stiff or pliable the bot's identity feels.

---

## 4. Wiring in `GlobalWorkspace`

`core/global_workspace.py` instantiates the vault and the engine eagerly:

```python
self.vault = SvalbardVault()
self.vault.verify_identity_integrity(full_chain=False)
self.pedi = PEDIEngine(self.vault)
self._self_check_diagnostics(self.pedi, self.vault)
```

Failure of `_self_check_diagnostics` calls `sys.exit(1)` — the workspace
treats missing vault/regulator as a hard fault.

The end-to-end interaction lives in `execute_cli_cycle`:

```
raw_active_state ──► PEDI.evaluate_cycle ──► regulated_state, status
                                          │
                                          ▼
                                 generate_response_func(user_input, regulated_state)
                                          │
                                          ▼
              status == "EVOLVING" or resonance > 0.90?
                                          │
                                  Lantern-4 veto (see below)
                                          │
                              approved? ──► vault.deposit_core_memory(...)
                                          │
                                          ▼
                          return sys_response, regulated_state, status
```

### 4.1 Lantern-4 veto

`GlobalWorkspace._lantern_4_veto` decides whether a milestone is allowed
into the vault. It returns `(approved, quarantine)`:

| Gate | Effect |
|---|---|
| `resonance < 0.85` | Rejected outright — only deep contact qualifies. |
| `resonance < 0.95` and either side is short (<5 user words or <10 system words) | Rejected as lacking semantic density. |
| `shadow_depth > 0.75` | Approved *but* `quarantined=True` so PEDI ignores it when computing the gravity center. |

The quarantine flag means the bot can *remember* messy breakthroughs without
letting them re-anchor identity until they've been integrated elsewhere.

---

## 5. Operational notes

- **Backups.** Treat `<VAULT_PATH>` and `<VAULT_PATH>.sig` as a unit. Copy
  both atomically or the signature will mismatch on the next startup.
- **Restoring on a new host.** Move both files **and** set
  `DRIFT_VAULT_SECRET` to the original secret value. Without the secret,
  signature verification will fail on startup.
- **Empty / fresh installs.** A non-existent ledger is fine; `latest_hash`
  initializes to `"0" * 64` and the first block chains from there.
- **Tampering with the JSONL by hand.** Don't. The next startup will either
  fail signature verification (if you keep the `.sig`) or reset
  `latest_hash` to a wrong value (if you don't). If you must edit, rebuild
  the chain offline and re-sign with `_sign_root_hash`.
- **PEDI tuning.** The constants in `evaluate_cycle` materially change
  identity stiffness. If responses start feeling "wobbly," lower the
  reaction weight or raise the evolution-gate threshold; if they feel
  "stuck," do the opposite.
- **High-throughput deployments.** Both `_sign_root_hash` and
  `deposit_core_memory` call `os.fsync()`. If the main thread blocks on
  vault writes under load, route deposits through an async queue (the
  module already flags this with a TODO).

---

## 6. Related

- [`HOW_INFJ_BOT_WORKS.md`](HOW_INFJ_BOT_WORKS.md) — overall chat-turn flow.
- [`SECURITY_DEFENSE.md`](SECURITY_DEFENSE.md) — input-side defense; this
  document is its post-response, persistence-side counterpart.
- [`DMU_PEDI_TEST_PLAN.md`](DMU_PEDI_TEST_PLAN.md) — testing methodology for
  the **other** PEDI (`metrics/pedi.py`) and for DMU.
- [`GLOSSARY.md`](GLOSSARY.md) — terms for IdentityBlock, EmotionalAnchor,
  Lantern-4, gravity center.
