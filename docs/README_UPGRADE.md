# DRIFT Upgrade — Pre-Test Execution Guide
## Complete, Ordered Steps. No improvising.

> **Status:** Modules are already wired into `core/`. This guide is the
> operational discipline for running ablations against them. For an
> overview of *what each module does*, see [SUBSYSTEMS.md](SUBSYSTEMS.md).

---

## Files in This Package

| File | Purpose |
|------|---------|
| `core/run_logger.py` | Thread-safe SQLite logger (deadlock-free, WAL mode) |
| `core/experiment_control.py` | Freeze-mode infrastructure + ablation discipline |
| `core/dmu_scoring.py` | Additive MPS (Memory Prioritization Score) with `score_components` |
| `core/hook_wiring.py` | Reference patterns for `memory.py`, `homeostasis.py`, `cognition.py` |
| `core/continuity_vector.py` | Five-axis continuity scoring + baseline normalization |
| `tests/collect_baseline.py` | Baseline session runner (companion / task / exploration) |
| `tests/ablation_runner.py` | Single-test ablation runner (`--test identity_collapse` etc.) |
| `tests/ablation_suite.py` | Full 6-condition (A–F) ablation suite |
| `tests/inspect_logs.py` | Database inspector for `experiment_log.db` verification |
| `FALSIFIABILITY.md` | Committed falsifiability statement — do not modify after baseline |

---

## Execution Order (do not skip steps)

### PHASE 1 — Infrastructure

**Step 1: Verify the modules are present**

The five core modules ship under `core/`; they are *not* root-level files.
Confirm with:
```bash
ls core/run_logger.py core/experiment_control.py core/dmu_scoring.py \
   core/hook_wiring.py core/continuity_vector.py
```

If any are missing your branch is out of sync. Pull `master`.

**Step 2: Confirm `MPS_WEIGHTS` lives in a stable location**

`core/dmu_scoring.MPS_WEIGHTS` is the current location. If your fork has
moved it to `core/config.py`, make sure every importer reads from the same
place — weight location must be stable for the run to be reproducible.

**Step 3: Confirm the three core hooks are wired**

`core/hook_wiring.py` is a reference document, not a drop-in. The patterns
it documents must be present at:
- `core/memory.py` — memory store call site, guarded by `control.is_active("memory")`
- `core/homeostasis.py` — state update call site, guarded by `control.is_active("state")`
- `core/cognition.py` — novelty computation, freeze check **before** propagation to memory object

Rules:
- DO NOT wire `core/self_modify.py` yet — it must stay frozen in all initial test configs.
- Freeze novelty at *computation* time, not after caching. A cached novelty score that the freeze switch missed silently preserves the system under test.

**Step 4: Wire stub functions in `core/dmu_scoring.py`**

Confirm these are bound to real implementations:
- `_normalized_contextual_sim()` → your embedding/keyword similarity
- `_state_alignment_score()` → your homeostasis-deficit alignment
- `_chromadb_results_to_memories()` → your `Memory` class factory

**Step 5: Wire stub functions in baseline / ablation runners**

`tests/collect_baseline.py` and `tests/ablation_runner.py` both contain a
`_extract_continuity_axes()` stub. Wire it to your NLP layer (spaCy
entities, embedding cosine for tone, etc.). See `core/continuity_vector.py`
for operationalization notes per axis.

---

### PHASE 2 — Verification

**Step 6: Run one unfrozen session manually**

Run DRIFT normally (not via `tests/ablation_runner.py`) for 20–30 turns.
After the session, run:
```bash
python tests/inspect_logs.py
```

Verify ALL of the following are present:
- [ ] run_id in runs table
- [ ] git_hash (not "unknown" if in git repo)
- [ ] config logged
- [ ] state_snapshot events present
- [ ] memory_selection events present
- [ ] score_components present in selected memories
- [ ] rejected candidates logged
- [ ] continuity_metrics events present (all 5 axes)
- [ ] run_end event present

**If anything is missing: stop. Fix the wiring. Re-run. Do not proceed.**

---

### PHASE 3 — Baseline Collection

**Step 7: Run three baseline sessions**
```bash
python tests/collect_baseline.py
```

This runs companion, task, and exploration mode sessions automatically.
Pools data and saves `drift_baseline_stats.json`.
Output will show variance check results per axis.

**If any axis fails variance check: stop. Fix the metric. Re-run.**

**Step 8: Check axis correlations**
After baseline, run correlation check using data from the baseline sessions.
See `continuity_vector.check_axis_correlation()`.
If any pair shows r > 0.6, investigate before proceeding.

---

### PHASE 4 — Ablation Runs

**Step 9: Read FALSIFIABILITY.md**
Read it. It defines what results mean before you see them.
Do not run ablations without having read it.

**Step 10: Identity Collapse run**
```bash
python tests/ablation_runner.py --test identity_collapse
```

After run: inspect logs. Do not interpret yet.

**Step 11: Scrambled Memory run**
```bash
python tests/ablation_runner.py --test scrambled_memory
```

**Step 12: Reintroduction Curve**
```bash
python tests/ablation_runner.py --test reintroduction_curve
```

**Step 13: Compute effect sizes**
Use `ablation_runner.compute_effect_sizes()` with baseline and ablation results.
Report Cohen's d per axis. Thresholds defined in FALSIFIABILITY.md.

**Step 14 (optional): Full 6-condition suite**

For the published ablation table (A–F: No Council, No Shadow, No Homeostasis,
Cosine-only RAG, Local-LLM-only, Full Stack), use:
```bash
python tests/ablation_suite.py --conditions A,B,C,D,E,F --prompts 50 --live
```

Results are written to `ABLATION_RESULTS/ablation_<timestamp>_<condition>.json`
plus a `_summary.txt` and `_methodology.md` per run. See
`ABLATION_RESULTS/ABLATION_FINDINGS_EXPLAINED.md` for the interpretation
framework.

---

## Absolute Rules (enforced by code or by discipline)

1. Never run mutation + self_modify + DMU changes simultaneously during testing.
2. Never start a new run without calling end_run() first.
3. Never skip the log inspection step (Step 6).
4. Never run ablations before baseline variance is validated (Step 7).
5. Never move the effect size goalposts after seeing results.
6. Never modify FALSIFIABILITY.md after baseline runs begin.
7. Keep codebase on a stable git commit during each ablation run.
   Branch → freeze → run → merge.

---

## Hardware Notes (OmniSlim CPU-only)

- Sparse counterfactual PEDI: run only on high-variance turns or every N turns.
  Not every turn. Your CPU will not survive it.
- Two-stage retrieval (ChromaDB wide pull → DMU rerank) is the correct pattern.
  Do not try to make ChromaDB do the full scoring.
- Score caching: use `state_hash + node_id + session_id` as cache key.
  Invalidate only when state_delta > threshold or reinforcement updated.
- Metabolism thread: idle-only (30-60 min intervals). Not in the hot path.
- Ollama qwen3:4b fallback: budget for 500%+ CPU under load.
  Do not run ablations during heavy system load.

---

## After the Ablation Suite

Once effect sizes are computed and results are in:
- Document findings against FALSIFIABILITY.md interpretation framework.
- Only then: implement mutation (with dual-anchor + founding_summary).
- Only then: implement dream compression.
- Only then: wire self_modify hooks.

Each of these adds a new drift vector. Add them one at a time with freeze-mode
ablations between additions.

---

## The Question You're Actually Answering

> "Which components of continuity emerge under controlled memory conditions,
>  and what do state and memory each independently contribute?"

Everything in this package is instrumentation for that question.
The answer is whatever the data shows.
