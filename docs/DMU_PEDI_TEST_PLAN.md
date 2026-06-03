# DMU & PEDI Testing Methodology

> **Last updated:** 2026-06-03
> **Status:** Modules implemented; `tests/test_pedi.py` and `tests/test_comonad.py`
> now cover anchor math, hold states, and the comonadic pipeline. DMU unit tests
> still pending.

---

## ⚠️ "PEDI" disambiguation

This repo currently contains **two** distinct modules whose names start with
"PEDI". They measure different things and have separate test surfaces. Do not
mix them up.

| Module                                  | Class         | Measures                                                | Runtime role                                                                |
|-----------------------------------------|---------------|---------------------------------------------------------|------------------------------------------------------------------------------|
| `core/pedi_metrics.py`                  | `PEDIEngine`  | Identity drift against a Svalbard-ledger anchor (3-D).  | Production. Wired into `GlobalWorkspace.execute_cli_cycle` Fly-By-Wire path. |
| `metrics/pedi.py`                       | `PediIndex`   | State **fluidity** across context-window resets (7-D).  | Optional telemetry / research instrument. Not on the chat hot path.          |

Sections 2 and 3 below cover the *research* implementations (`memory/dmu.py`
and `metrics/pedi.py`). For the production identity regulator, the comonadic
pipeline, and the Lantern-4 seal flow, see
[IDENTITY_REGULATOR.md](IDENTITY_REGULATOR.md) and
[COMONADIC_BRIDGE.md](COMONADIC_BRIDGE.md).

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

## 2. PEDI fluidity instrument (`metrics/pedi.py`)

> This is the *research* PEDI — **Performance & Efficiency Detection Index**.
> The production identity regulator (`core/pedi_metrics.py`) is documented
> separately in [IDENTITY_REGULATOR.md](IDENTITY_REGULATOR.md).

`metrics/pedi.py` measures **state fluidity** across context-window resets using Euclidean jump detection:

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
