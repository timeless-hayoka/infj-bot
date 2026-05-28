# Identity Regulator — Svalbard Vault & PEDI Engine

This document describes the **identity persistence and regulation layer** added to DRIFT in May 2026. Together, the **Svalbard Vault** and the **PEDI Engine** form a "fly-by-wire" stabilizer around the bot's emotional/cognitive state: every cycle the workspace consults a long-term anchor, gently corrects toward it, and — when the bot lives through a milestone moment — seals that moment into a tamper-evident ledger.

**Source files**

| File | Role |
|------|------|
| [`core/svalbard_vault.py`](../core/svalbard_vault.py) | Hash-chained, HMAC-signed JSONL ledger of "core memories" |
| [`core/pedi_metrics.py`](../core/pedi_metrics.py) | Persistence-Embodiment-Drift Index regulator |
| [`core/global_workspace.py`](../core/global_workspace.py) | Integrates both via `execute_cli_cycle` and the Lantern-4 veto |

---

## 1. Why this layer exists

Plain LLM chat history is fragile: any noisy turn can re-anchor the bot's tone. DRIFT's other state (Chroma memories, SQLite "state brains") drifts continuously by design and is **not** the right place to assert "this is who I am." The identity regulator separates two responsibilities:

- **`SvalbardVault`** — write-once, append-only **identity ledger**. Each `IdentityBlock` is hashed and chained to the previous block; the latest hash is signed with HMAC-SHA256. Only **vetted** milestone exchanges get sealed.
- **`PEDIEngine`** — every cycle, takes the raw emotional state (`coherence`, `resonance`, `tension`, `shadow_depth`) and pulls it toward the **center of gravity** computed from the vault's recent **un-quarantined** blocks.

The pair is sometimes referred to in code/logs as the **"regulatory triad"** alongside the global workspace.

---

## 2. The Svalbard Vault

### 2.1 Storage layout

The vault writes JSONL — one `IdentityBlock` per line — to a path resolved in this order:

1. Environment variable `DRIFT_VAULT_PATH` (absolute path).
2. `DATA_ROOT / "svalbard_ledger.jsonl"` (when `infj_bot.core.config` is importable).
3. Fallback: `~/.drift_os/svalbard_ledger.jsonl`.

The HMAC signature of the latest chain root is written to `<VAULT_PATH>.sig`. The HMAC secret comes from `DRIFT_VAULT_SECRET` and falls back to a development default that triggers a warning on startup.

### 2.2 Block schema

```python
@dataclass
class EmotionalAnchor:
    coherence: float
    tension: float
    resonance: float
    shadow_depth: float

@dataclass
class IdentityBlock:
    timestamp: str            # UTC ISO 8601
    event_summary: str        # e.g. "CLI Milestone: <first 40 chars>..."
    user_quote: str
    system_quote: str
    emotional_state: EmotionalAnchor
    prior_hash: str           # 64-hex parent (or 64 zeros for genesis)
    quarantined: bool = False
    version: str = "2.0"
    block_hash: str = ""      # SHA-256 of the canonical payload
```

`calculate_hash()` serializes a canonical subset with `sort_keys=True` and `separators=(',', ':')`. Identical inputs always produce the same hash, regardless of dict ordering.

### 2.3 Integrity guarantees

`SvalbardVault.verify_identity_integrity(full_chain: bool = False)`:

- Always checks the **signature** of the latest hash against the on-disk `.sig`. A mismatch logs `[CRITICAL SECURITY FAILURE]` and returns `False`.
- When `full_chain=True`, walks the entire JSONL, recomputes each block's hash from its declared fields, and verifies the `prior_hash` link. Any divergence returns `False`.

The workspace runs this **without** `full_chain` on startup; a full audit is a manual operation (CI, recovery, forensics).

### 2.4 Writing a block

```python
vault.deposit_core_memory(
    event="CLI Milestone: First successful drift cycle...",
    user_q=user_input,
    sys_q=sys_response,
    current_state={"coherence": 0.91, "tension": 0.18, "resonance": 0.95, "shadow_depth": 0.4},
    quarantined=False,   # set True if shadow_depth > 0.75
)
```

This is **not** called every turn. It is only triggered by the Lantern-4 veto (see §4).

After append, the file is `flush()`ed and `fsync()`ed, then the new HMAC signature is written and `fsync()`ed. The latest hash is cached in `vault.latest_hash`.

> **Performance note:** the code includes a `TODO OPTIMIZATION` comment about `os.fsync` blocking the main thread under high write rates. For low-frequency milestone writes (the expected pattern), the cost is negligible.

---

## 3. The PEDI Engine

PEDI stands for **Persistence-Embodiment-Drift Index**. It is a tuned closed-loop regulator over the four-axis emotional state. Each call to `evaluate_cycle(raw_active_state)` returns:

```python
(regulated_state: dict, applied_correction: float, status: str)
```

Where `status` is one of `NO_ANCHOR`, `EVOLVING`, `CORRECTING`, or `STABLE`.

### 3.1 Step-by-step

1. **Anchor lookup** — `_get_identity_center_of_gravity()` reads the last 20 lines of the vault, skips quarantined blocks, and computes a **weight-averaged** anchor where each block's weight is `resonance * coherence`. If no anchored blocks exist yet, a static default is returned. If the vault file is missing entirely, the engine returns `(raw_state, 0.0, "NO_ANCHOR")` and does nothing.
2. **Perception smoothing** — `perceived_state ← 0.4·perceived + 0.6·raw`. This dampens high-frequency noise so the regulator does not chase single-turn spikes.
3. **Drift measurement** — Euclidean distance between `perceived_state` and the anchor, normalized to `[0, 1]` via `min(1.0, dist / 2.0)`.
4. **Improvement score** — `0.5·Δcoherence + 0.4·Δresonance − 0.1·Δtension` (positive = the bot is moving in a "better" direction than the anchor).
5. **Integral windup guard** — `meta_drift_accumulator ← accumulator · 0.98` every cycle.
6. **Evolution gate** — if `instant_drift > 0.28` **and** `improvement_score > 0.05`, the engine **does not correct**. It returns status `"EVOLVING"` and decays the accumulator hard (`× 0.3`). This is how the bot is allowed to grow rather than be clamped to its past self.
7. **Meta-drift accumulation** — otherwise, `accumulator += instant_drift · 0.1` (capped at 1.0).
8. **Correction** — `raw_correction_weight = min(0.85, (instant_drift + accumulator)²)`, then a smooth reaction weight of `0.22` is applied. If the resulting correction `> 0.05`, the engine blends the perceived state toward the anchor (status `"CORRECTING"`) and decays the accumulator (`× 0.7`). Below threshold: status `"STABLE"`, no mutation.

### 3.2 Constants and tuning

| Symbol | Value | Meaning |
|--------|-------|---------|
| `perception_weight` | `0.6` | Blend factor for raw → perceived state |
| `accumulator decay` | `0.98` | Per-cycle windup damping |
| `evolution drift threshold` | `0.28` | Above this + improving → unclamp |
| `evolution improvement threshold` | `0.05` | Required `(c, r, t)` delta to qualify as growth |
| `meta accumulation rate` | `0.10` | Fraction of `instant_drift` added per cycle |
| `correction cap` | `0.85` | Max raw correction weight before reaction blending |
| `reaction weight` | `0.22` | Final blend factor applied to the correction |
| `correction floor` | `0.05` | Below this, no state mutation occurs |

These were "tuned per long-run data" per the source. Re-tune by editing `core/pedi_metrics.py` and re-running long-form ablations.

---

## 4. Integration with Global Workspace

`GlobalWorkspace.__init__` constructs both objects and runs a diagnostics check that will `sys.exit(1)` if either is missing (`_self_check_diagnostics`). This is intentional — DRIFT will not run without its identity regulator.

The combined cycle lives in `GlobalWorkspace.execute_cli_cycle(raw_active_state, user_input, generate_response_func)`:

```text
1. regulated_state, correction, status = pedi.evaluate_cycle(raw_active_state)
2. sys_response = generate_response_func(user_input, regulated_state)
3. If status == "EVOLVING" or regulated_state.resonance > 0.90:
     approved, quarantine = _lantern_4_veto(user_input, sys_response, regulated_state)
     if approved:
         vault.deposit_core_memory(...)
4. return sys_response, regulated_state, status
```

### Lantern-4 veto

`_lantern_4_veto` is the gatekeeper that decides whether an exchange is "core memory" material. It returns `(approved, quarantine)`:

- **Resonance gate.** `resonance < 0.85` → rejected outright.
- **Semantic density gate.** Unless `resonance >= 0.95` (the override), the exchange must include at least 5 input words and 10 response words. Single-word exchanges cannot anchor identity.
- **Shadow quarantine.** If `shadow_depth > 0.75`, the block is still admitted but `quarantine=True`. Quarantined blocks are stored, hashed, and chained — but they are **ignored** by PEDI's anchor computation, so they cannot pull the bot toward a destabilizing center of gravity.

The veto logs `[LANTERN-4] ...` lines to stdout so you can audit acceptance from the CLI/web logs.

---

## 5. Operational guidance

### 5.1 Required environment

| Variable | Default | Notes |
|----------|---------|-------|
| `DRIFT_VAULT_PATH` | `${INFJ_DATA_DIR}/svalbard_ledger.jsonl` (else `~/.drift_os/svalbard_ledger.jsonl`) | Where the ledger lives. Treat as sensitive — it contains user/system quotes. |
| `DRIFT_VAULT_SECRET` | `default_dev_secret_do_not_use_in_prod` | HMAC key for chain-root signing. **Override in any non-dev deployment.** Startup logs a `[⚠️ WARNING]` when the default is detected. |

The `.sig` file lives next to the ledger as `<VAULT_PATH>.sig`. Keep both together when moving or backing up.

### 5.2 Backup & recovery

- The ledger is plain JSONL — copy it. There is no compaction. Append-only.
- If you rotate `DRIFT_VAULT_SECRET`, the existing `.sig` becomes invalid and `verify_identity_integrity()` will fail. Either keep the old secret or re-sign by appending one trivial block under the new key.
- To **audit** a vault from outside the bot:
  ```python
  from infj_bot.core.svalbard_vault import SvalbardVault
  v = SvalbardVault()
  assert v.verify_identity_integrity(full_chain=True), "chain broken"
  ```
- To **wipe identity** for a fresh start: stop the process, delete `VAULT_PATH` and `VAULT_PATH.sig`. The next startup will write a new genesis block (when one earns Lantern-4 approval).

### 5.3 Inspecting the ledger

Each JSONL line is a full `IdentityBlock` (with the dataclass `asdict()` output). Quick CLI inspection:

```bash
jq -c '{ts: .timestamp, summary: .event_summary, hash: .block_hash[0:12], q: .quarantined}' "$DRIFT_VAULT_PATH"
```

### 5.4 Common pitfalls

- **"Bot feels flat / over-corrected."** PEDI is pulling the state toward an anchor that doesn't match the current arc. Either (a) wait — Lantern-4 will admit a new milestone if resonance climbs back above 0.85, or (b) inspect the ledger and quarantine outdated anchors manually (rewrite the line with `"quarantined": true`).
- **"Nothing ever gets sealed."** Check stdout for `[LANTERN-4] Rejected` lines. The most common cause is `resonance < 0.85`, which means upstream emotion scoring is undershooting. The vault is intentionally conservative; it would rather skip a milestone than seal noise.
- **"`[CRITICAL SECURITY FAILURE] Signature mismatch` on every boot."** The `.sig` file is stale or `DRIFT_VAULT_SECRET` changed. Re-derive: load the latest block from the JSONL, recompute its hash, sign it with the current secret, and write `.sig`. Until then, `verify_identity_integrity()` returns `False` (the bot still runs — the result is logged, not enforced — but downstream audits should treat the ledger as untrusted).
- **`NO_ANCHOR` status persisting.** The ledger is empty or unreadable. The bot will keep using the raw active state until at least one block has been sealed.

---

## 6. Cross-references

- Workspace integration and tiered attention: [HOW_INFJ_BOT_WORKS.md § Strong Continuous Mode](HOW_INFJ_BOT_WORKS.md#36-strong-continuous-mode-background-drift-cycles).
- Terms (`Svalbard Vault`, `PEDI`, `Lantern-4`, `Identity Block`, `Quarantined memory`): [GLOSSARY.md](GLOSSARY.md).
- Secret hygiene for `DRIFT_VAULT_SECRET`: [`SECURITY.md`](../SECURITY.md).
