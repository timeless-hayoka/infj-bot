# DMU & PEDI Testing Methodology

> **Last updated:** 2026-06-03
> **Status:** DMU and the continuity PEDI (`metrics/pedi.py`) are wired into `cognitive_orchestrator.py`. The regulation PEDI (`core/pedi_metrics.py`) is wired into `core/global_workspace.py` and the optional comonadic chat path. `tests/test_pedi.py` covers the continuity PEDI. No tests yet exist for the regulation PEDI or DMU.

---

## Two distinct "PEDI" systems

The codebase has **two** modules using the PEDI acronym. They do **not** interact and must be kept separate when writing tests or reading metrics.

| Aspect | **Continuity PEDI** | **Regulation PEDI** |
|---|---|---|
| Module | `metrics/pedi.py` (`PediIndex`) | `core/pedi_metrics.py` (`PEDIEngine`) |
| Acronym expansion | Performance & Efficiency Detection Index | Persistence-Embodiment-Drift Index |
| State space | 7-need homeostasis vector | 3-dim `coherence` / `resonance` / `tension` (with `shadow_depth` tracked but excluded from anchor distance) |
| Question it answers | "Did the bot's internal state jump implausibly across a context-window reset?" | "Is the bot's emotional state drifting away from its identity center-of-gravity, and how hard should we pull it back?" |
| Wiring point | `CognitiveOrchestrator.assemble_prompt` records snapshots pre/post `trim_to_budget()` | `GlobalWorkspace.execute_cli_cycle` runs `evaluate_cycle` to produce a `regulated_state` before generation |
| Telemetry | `data/pedi.db` (SQLite) | In-memory `meta_drift_accumulator` + Svalbard ledger reads |
| Outputs | Fluidity score `SFS_k`, cumulative `CF_t`, crisis flag | Status string (`STABLE` / `CORRECTING` / `EVOLVING` / `HOLD_*`), correction weight, regulated state vector |

Always cite the **module path** (`metrics/pedi.py` vs `core/pedi_metrics.py`) in design discussions to avoid ambiguity.

---

## 1. DMU (Dynamic Memory Unit) Testing

The DMU lives at `memory/dmu.py` and provides an **alternative time-decay ranking model** on top of the Unified Memory Spine's existing `_calculate_dmu()`. It uses an emotionally-dampened exponential retention curve:

```
R(t, E) = e^(-λ_base * t / (1 + α * E))
MPS = w_sim * S + w_time * R + w_emo * E + w_rec * recency
```

### Implemented
- `DynamicMemoryUnit.rank_memories()` — re-ranks `MemoryEntry` objects from the spine
- `DriftMemory.retrieve_context_ranked()` — prompt-builder integration with fallback
- SQLite telemetry logging (`data/dmu.db`)

### Test Cases (to be written in `tests/test_dmu.py` — **not yet present**)
- **Exponential Decay Verification:** Verify `R(t, E)` decreases monotonically with `t` and increases with `E`.
- **Emotional Damping Test:** High-emotion memories (`E=1`) should decay at ~1/3 the rate of neutral memories (`E=0`) when `α=2`.
- **MPS Bounds:** Confirm `MPS ∈ [0, 1]` for all valid inputs.
- **Fallback Safety:** If `rank_memory_entries()` throws, `retrieve_context_ranked()` must fall back to plain retrieval.
- **Integration:** Call `assemble_prompt()` and verify DMU-ranked context appears in the final prompt string.

---

## 2. Continuity PEDI Testing — `metrics/pedi.py`

`PediIndex` measures **state fluidity** across context-window resets using Euclidean jump detection over a 7-need homeostatic vector:

```
Δ_k = ||s_post - s_pre||_2
SFS_k = max(0, 1 - Δ_k / Δ_max)
CF_t  = β * CF_{t-1} + (1 - β) * SFS_t   (β = 0.9)
```

A `crisis_flag` fires when `CF_t < CRITICAL_FLUIDITY`.

### Implemented
- `PediIndex.evaluate_reset()` — compares pre/post homeostatic snapshots
- `PediIndex.record_snapshot()` — turn-level state persistence
- Crisis flagging when cumulative fluidity drops below the critical threshold
- SQLite telemetry logging (`data/pedi.db`)
- Wired into `CognitiveOrchestrator.assemble_prompt()` pre/post `trim_to_budget()`

### Test Cases — `tests/test_pedi.py` (all **passing**)
- `test_record_and_get_last_snapshot` — snapshot round-trips through SQLite.
- `test_zero_jump` — identical state vectors → `SFS = 1.0`, `recovered = True`, no crisis.
- `test_max_jump` — `Δ_k ≥ Δ_max` → `SFS = 0.0`.
- `test_ema_smoothing` — verifies `CF_t = 0.9 * CF_{t-1} + 0.1 * SFS_t`.
- `test_crisis_trigger` — alternating min/max needs drive `CF_t` below `CRITICAL_FLUIDITY` and assert `crisis_flag = True`.
- `test_cognitive_orchestrator_integration` — patches `get_pedi` and confirms a snapshot is recorded on each `assemble_prompt` call with the correct `turn_id`.

Run with:

```bash
pytest tests/test_pedi.py -v
```

---

## 3. Regulation PEDI Testing — `core/pedi_metrics.py`

`PEDIEngine` reads the last 20 sealed `IdentityBlock` entries from the Svalbard ledger, computes a resonance × coherence weighted **center of gravity** (the "identity anchor"), and uses it to regulate the raw active state each cycle.

Anchor distance is computed in 3D over `DIMS = ("coherence", "resonance", "tension")`. `shadow_depth` is **intentionally excluded** from `DIMS` so the anchor math matches the paper's 3D state-space model, even though Svalbard blocks store all four axes (see the comment block at the top of `core/pedi_metrics.py`).

Outputs each call to `evaluate_cycle(raw_active_state)`:

| Status | Meaning |
|---|---|
| `STABLE` | No correction applied |
| `CORRECTING` | Pulls state back toward the anchor (applied_correction > 0.05) |
| `EVOLVING` | High drift but `improvement_score > 0.05` — the engine lets the state evolve and partially resets `meta_drift_accumulator` |
| `HOLD_<REASON>` | Anchor unavailable; state is returned unchanged. Reasons include `NO_VAULT`, `NO_BLOCKS`, `COLD_START`, `READ_ERROR: ...` |

### Implemented
- `_get_identity_center_of_gravity` returns `AnchorResult(anchor, valid, reason)` (refactored 2026-05-31).
- Quarantined and degenerate blocks are filtered out of the usable set.
- `MIN_USABLE_BLOCKS = 3`; below that the engine returns the deterministic `FALLBACK_ANCHOR` and a `HOLD_COLD_START` status.
- Perception smoothing (0.6 weight), evolution gate (`drift > 0.28 and improvement > 0.05`), integral-windup damping (0.98), and reaction-weight smoothing (0.22) all live in `evaluate_cycle`.
- Wired into `GlobalWorkspace.execute_cli_cycle` and consulted by the comonadic chat path in `interfaces/main.py` for vault-deposit gating.

### Test Cases (to be written in `tests/test_pedi_engine.py` — **not yet present**)
- **Cold start:** ledger missing or fewer than 3 usable blocks → `HOLD_COLD_START`, anchor equals `FALLBACK_ANCHOR`.
- **Read error:** corrupt JSONL line → `HOLD_READ_ERROR: ...` with anchor equal to `FALLBACK_ANCHOR` and no exception leaking.
- **Quarantined blocks excluded:** seed 5 blocks of which 3 are `quarantined=True` and confirm they do not influence the anchor.
- **Degenerate blocks excluded:** blocks with both `coherence` and `resonance` below `1e-6` must not contribute weight.
- **Weighted average sanity:** with two non-quarantined non-degenerate blocks plus a third, the anchor matches the expected `resonance * coherence` weighted mean for each `DIMS` axis.
- **Status transitions:**
  - Identical state to anchor → `STABLE`.
  - State 0.4 away from anchor with `improvement_score < 0.05` → `CORRECTING` and `meta_drift_accumulator` rises but is capped at 1.0.
  - State 0.3 away with positive coherence/resonance deltas → `EVOLVING`.
- **Shadow exclusion invariant:** mutating only `shadow_depth` between turns must not change `instant_drift`.

---

## 4. Cross-cutting tests (Svalbard vault + PEDI engine)

`docs/VAULT_STABILITY_NOTES.md` lists the still-open hardening items for the regulation path:

1. `tests/test_vault.py` — hash chain verification, tampered-block detection, missing/corrupt ledger graceful degradation.
2. Replace `sys.exit(1)` in `GlobalWorkspace._self_check_diagnostics` with a degraded-mode fallback.
3. Add `/vault status` or `/pedi status` slash command surfacing latest hash, current status, accumulator, and integrity result.
4. Ensure `DRIFT_VAULT_SECRET` is set per-deployment (the default value is intentionally insecure).

---

## 5. Research alignment

Both regulation PEDI and DMU align with the cognitive research synthesized in `research_from_gemini.md`:

| Research | Implementation |
|---|---|
| CAEEMA (Cardoso & Campos, 2025) — emotional decay mechanics | DMU: logarithmic retention + emotional damping |
| Abdulhai et al. NeurIPS 2025 — trajectory-level consistency | Continuity PEDI: measures state continuity across context resets |
| Persistent identity anchors under drift | Regulation PEDI: Svalbard-anchored Fly-By-Wire correction |

---

## 6. Running the audit

```bash
export GEMINI_API_KEY="your-key"
python3 verify_architecture.py
pytest tests/test_pedi.py -v       # continuity PEDI
pytest tests/test_comonad.py -v    # comonadic pipeline (drives the regulation 4-axis state)
```

`verify_architecture.py` validates the inline mathematical documentation for both modules. The two `pytest` invocations are independent and can run on a checkout without API keys.
