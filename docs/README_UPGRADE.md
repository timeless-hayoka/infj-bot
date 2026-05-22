# DRIFT Upgrade — Pre-Test Execution Guide
## Complete, Ordered Steps. No improvising.

---

## Files in This Package

| File | Purpose |
|------|---------|
| `run_logger.py` | Thread-safe SQLite logger (deadlock-free) |
| `experiment_control.py` | Freeze-mode infrastructure + ablation discipline |
| `dmu_scoring.py` | Corrected additive MPS with score_components |
| `hook_wiring.py` | Reference patterns for memory.py, homeostasis.py, cognition.py |
| `continuity_vector.py` | Five-axis continuity scoring + baseline normalization |
| `collect_baseline.py` | Baseline session runner |
| `ablation_runner.py` | Ablation test suite |
| `inspect_logs.py` | Database inspector for log verification |
| `FALSIFIABILITY.md` | Committed falsifiability statement — do not modify after baseline |

---

## Execution Order (do not skip steps)

### PHASE 1 — Infrastructure

**Step 1: Copy files into DRIFT codebase**
```
run_logger.py          → your project root or utils/
experiment_control.py  → your project root or utils/
dmu_scoring.py         → wire into your existing DMU/memory module
```

**Step 2: Move MPS_WEIGHTS to your config**

In `dmu_scoring.py`, MPS_WEIGHTS is marked for relocation.
Move it to `config.py` or your existing config module.
Import from there in dmu_scoring.py.
Do this before wiring MPS — weight location must be stable.

**Step 3: Wire the three core hooks**

Open `hook_wiring.py` and apply the patterns to:
- `memory.py` — memory store call site
- `homeostasis.py` — state update call site
- `cognition.py` — novelty computation (BEFORE memory.novelty_score is set)

Rules:
- `if control.is_active("memory"):` wraps memory storage
- `if control.is_active("state"):` wraps homeostasis updates
- novelty: freeze check must happen BEFORE propagation to memory object
- DO NOT wire self_modify.py yet — frozen in all initial test configs

**Step 4: Wire stub functions in dmu_scoring.py**

The following must be implemented against your actual codebase:
- `_normalized_contextual_sim()` → your embedding/keyword similarity
- `_state_alignment_score()` → your homeostasis deficit alignment
- `_chromadb_results_to_memories()` → your Memory class factory

**Step 5: Wire stub functions in collect_baseline.py and ablation_runner.py**

Both files have a `_extract_continuity_axes()` stub.
Wire it to your NLP layer (spaCy entities, embedding cosine for tone, etc.)
See continuity_vector.py for operationalization notes per axis.

---

### PHASE 2 — Verification

**Step 6: Run one unfrozen session manually**

Run DRIFT normally (not via ablation_runner) for 20-30 turns.
After the session, run:
```
python inspect_logs.py
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
```
python collect_baseline.py
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
```
python ablation_runner.py --test identity_collapse
```

After run: inspect logs. Do not interpret yet.

**Step 11: Scrambled Memory run**
```
python ablation_runner.py --test scrambled_memory
```

**Step 12: Reintroduction Curve**
```
python ablation_runner.py --test reintroduction_curve
```

**Step 13: Compute effect sizes**
Use `ablation_runner.compute_effect_sizes()` with baseline and ablation results.
Report Cohen's d per axis. Thresholds defined in FALSIFIABILITY.md.

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
