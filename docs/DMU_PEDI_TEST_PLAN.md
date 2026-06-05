# DMU & PEDI Testing Methodology

> **Last updated:** 2026-06-05
> **Status:** Core modules implemented and wired into `cognitive_orchestrator.py`. Unit tests partially in place (`tests/test_pedi.py`).

> **Heads-up — two PEDIs coexist.** This document covers the **state-fluidity** PEDI at
> `metrics/pedi.py` (the `PediIndex` class). A second, *separate* index — the
> **Persistence-Embodiment-Drift Index** (`PEDIEngine` in `core/pedi_metrics.py`) — was
> added later to drive Svalbard sealing and identity regulation in the global workspace.
> They share a name and an SQLite footprint pattern but solve different problems. See
> [VAULT_STABILITY_NOTES.md](VAULT_STABILITY_NOTES.md) and
> [COMONADIC_BRIDGE.md](COMONADIC_BRIDGE.md) for the identity-regulator PEDI.

---

## 1. DMU (Dynamic Memory Unit) Testing

The DMU lives at `memory/dmu.py` and provides an **alternative time-decay ranking model** on top of the Unified Memory Spine's existing `_calculate_dmu()`. It uses an emotionally-dampened exponential retention curve:

```
R(t, E) = e^(-λ_base * t / (1 + α * E))
MPS = w_sim * S + w_time * R + w_emo * E + w_rec * recency
```

### ✅ Implemented
- `DynamicMemoryUnit.rank_memories()` — re-ranks `MemoryEntry` objects from the spine
- `DriftMemory.retrieve_context_ranked()` — prompt-builder integration with fallback
- SQLite telemetry logging (`data/dmu.db`)

### 🧪 Test Cases (to be written in `tests/test_dmu.py`)
- **Exponential Decay Verification:** Verify `R(t, E)` decreases monotonically with `t` and increases with `E`
- **Emotional Damping Test:** High-emotion memories (E=1) should decay at ~1/3 the rate of neutral memories (E=0) when α=2
- **MPS Bounds:** Confirm MPS ∈ [0, 1] for all valid inputs
- **Fallback Safety:** If `rank_memory_entries()` throws, `retrieve_context_ranked()` must fall back to plain retrieval
- **Integration:** Call `assemble_prompt()` and verify DMU-ranked context appears in the final prompt string

---

## 2. PEDI (Performance & Efficiency Detection Index) Testing

The PEDI lives at `metrics/pedi.py` and measures **state fluidity** across context-window resets using Euclidean jump detection:

```
Δ_k = ||s_post - s_pre||_2
SFS = max(0, 1 - Δ_k / Δ_max)
CF_t = β * CF_{t-1} + (1 - β) * SFS_t
```

### ✅ Implemented
- `PediIndex.evaluate_reset()` — compares pre/post homeostatic snapshots
- `PediIndex.record_snapshot()` — turn-level state persistence
- Crisis flagging when cumulative fluidity drops below 0.6
- SQLite telemetry logging (`data/pedi.db`)
- Wired into `assemble_prompt()` pre/post `trim_to_budget()`

### 🧪 Test Cases (to be written in `tests/test_pedi.py`)
- **Zero Jump:** Identical state vectors → SFS = 1.0
- **Max Jump:** Δ_k ≥ Δ_max → SFS = 0.0
- **EMA Smoothing:** Verify CF_t updates correctly with β = 0.9
- **Crisis Trigger:** Simulate 5 consecutive low-SFS turns and confirm crisis flag
- **Integration:** Verify snapshot is recorded on every `assemble_prompt()` call

---

## 3. Research Alignment

Both modules align with the cognitive research synthesized in `research_from_gemini.md`:

| Research | Implementation |
|----------|----------------|
| CAEEMA (Cardoso & Campos, 2025) — emotional decay mechanics | DMU: logarithmic retention + emotional damping |
| Abdulhai et al. NeurIPS 2025 — trajectory-level consistency | PEDI: measures state continuity across context resets |

---

## 4. Running the Audit

```bash
export GEMINI_API_KEY="your-key"
python3 verify_architecture.py
```

This validates inline mathematical documentation for both modules.
