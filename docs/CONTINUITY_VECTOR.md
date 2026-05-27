# Continuity Vector — Behavioral Telemetry

`core/continuity_vector.py` holds two related instruments that share a file but answer different questions:

| Instrument | Question | Output |
|------------|----------|--------|
| **Five-Axis Continuity Vector** | "Is this response continuous with the prior session?" | Normalized z-scores per axis |
| **Three-Axis Triad** `[memory, state, novelty]` | "Which cognitive layers are engaged right now?" | Binary vector + pattern name |

Both are used inside the ablation suite (`tests/ablation_suite.py`) and the Observatory telemetry stream. The five-axis pipeline is what backs the **falsifiable continuity claims** in [FALSIFIABILITY.md](FALSIFIABILITY.md); the three-axis triad is the lightweight runtime probe surfaced to the dashboard.

---

## 1. Five-Axis Continuity Vector

### Axes

| Axis | What it measures | Wire to |
|------|------------------|---------|
| `entity_overlap`        | Jaccard overlap of named entities turn-to-turn | spaCy NER |
| `goal_overlap`          | Cosine similarity of stated goal embeddings | `AgencyState` + embeddings |
| `tone_similarity`       | Cosine similarity to a baseline tone vector | first+last sentence embedding |
| `memory_reference_rate` | Explicit + implicit references to prior context per response length | regex + entity diff |
| `state_influence`       | State-related vocabulary density (lowest weight) | need labels / mood terms |

The exact operationalization for each axis is documented at the bottom of the source file (search for "Axis Operationalization Notes") — it's the canonical reference for anyone wiring a new metric.

### Workflow

```
1. Run 3 baseline sessions (companion + task + exploration).
2. collect_baseline([s1, s2, s3])     →  writes drift_baseline_stats.json
3. validate_baselines(stats)          →  rejects any axis with std < 1e-3
4. During each ablation/test turn:
   compute_continuity_vector(raw_axes, baselines)
5. (Optional) check_axis_correlation(session)  →  flags |r| > 0.6 pairs
```

```python
from infj_bot.core.continuity_vector import (
    collect_baseline, load_baselines, compute_continuity_vector,
)

# Once per project, after 3 baseline sessions
stats = collect_baseline([companion_session, task_session, exploration_session])

# Per turn
baselines = load_baselines()
vec = compute_continuity_vector(
    response_data={
        "entity_overlap": 0.42,
        "goal_overlap": 0.38,
        "tone_similarity": 0.71,
        "memory_reference_rate": 0.05,
        "state_influence": 0.12,
    },
    baselines=baselines,
)
# vec == {"normalized": {axis: z, ...}, "raw": {axis: value, ...}}
```

### Hard guards

- **Variance floor** (`VARIANCE_FLOOR = 1e-3`). If any axis collapses below that std during baseline collection, `validate_baselines()` emits a `warnings.warn` per axis and returns the list of failed axes. Treat that as a **stop signal** — the metric is broken, not the model.
- **Per-axis bypass**. If `std < VARIANCE_FLOOR` at inference time, `compute_continuity_vector()` falls back to the raw value rather than producing a +∞ z-score.
- **Correlation check**. `check_axis_correlation(session_axis_data)` prints a pairwise matrix and tags `|r| > 0.6` pairs as `⚠️ HIGH CORRELATION` — run it once before interpreting ablation results so you know which axes might be measuring the same thing.

`drift_baseline_stats.json` is the durable artifact and is read on every run. It is **not** auto-rebuilt — re-run `collect_baseline()` whenever the prompt builder, memory store, or any axis extractor changes.

---

## 2. Three-Axis Triad `[memory, state, novelty]`

A binary runtime probe that fires every prompt-assembly cycle. Used by the Observatory to surface "what is the bot doing right now" and by `cognitive_orchestrator.py` to gate downstream behaviors.

### Thresholds (tunable at the top of the module)

| Hook | Active when | Threshold |
|------|-------------|-----------|
| **memory**  | `retrieved_notes_count > 0` **or** `history_depth > 5` | `MEMORY_NOTES_THRESHOLD = 0`, `MEMORY_DEPTH_THRESHOLD = 5` |
| **state**   | `coherence_score < 0.80` **or** `pulse_variance > 0.15` | `STATE_COHERENCE_THRESHOLD = 0.80`, `STATE_VARIANCE_THRESHOLD = 0.15` |
| **novelty** | `shadow_influence > 0.20` **or** `new_entities_detected > 0` | `NOVELTY_SHADOW_THRESHOLD = 0.20`, `NOVELTY_ENTITIES_THRESHOLD = 0` |

### Pattern names

The vector `(memory, state, novelty)` maps to a human-readable pattern:

| Vector | Pattern | Reading |
|--------|---------|---------|
| `(1, 0, 0)` | COMPANION   | Memory anchored, stable, familiar |
| `(0, 1, 0)` | REGULATED   | Homeostasis active, no new input |
| `(0, 0, 1)` | EXPLORER    | Novelty spike, state holding |
| `(1, 1, 0)` | TASK        | Memory + regulation, known territory under load |
| `(1, 0, 1)` | RESONANT    | Memory + novelty, creative synthesis |
| `(0, 1, 1)` | FRONTIER    | State fighting novelty, organism adapting |
| `(1, 1, 1)` | FULL COUNCIL | All layers engaged, max deliberation |
| `(0, 0, 0)` | QUIET       | Minimal cognitive load, resting state |

### Wiring (where each input comes from)

```python
CognitiveContext(
    retrieved_notes_count = memory.search(...) result count,
    history_depth         = len(ChatHistory),
    coherence_score       = homeostasis.coherence_need.current,
    pulse_variance        = homeostasis.variance_across_needs(),
    shadow_influence      = shadow_governance.state.shadow_influence,
    new_entities_detected = metacognition.novel_concept_counter,
    active_mode           = state.mode,
)
```

```python
from infj_bot.core.continuity_vector import (
    CognitiveContext, calculate_continuity_vector, ContinuityLog,
)

ctx = CognitiveContext(
    retrieved_notes_count=2, history_depth=8,
    coherence_score=0.95, pulse_variance=0.05,
    shadow_influence=0.05, new_entities_detected=0,
    active_mode="companion",
)
vec = calculate_continuity_vector(ctx, cycle=42)
# vec.as_list()      → [1, 0, 0]
# vec.pattern_name() → "COMPANION — memory anchored, stable, familiar"
```

### Session-level analysis

`ContinuityLog` accumulates vectors across a session and exposes:

| Method | Returns |
|--------|---------|
| `record(vec)`         | Appends vector dict |
| `trajectory()`        | Sequence of pattern names |
| `dominant_pattern()`  | Most-common pattern in the session |
| `to_json()`           | Full session report (id, started_at, count, dominant, trajectory, vectors) |

Use the trajectory to validate that a mode change actually produced a pattern shift — for example, switching `companion → drift` should move the dominant pattern from `COMPANION` toward `RESONANT` or `FRONTIER`.

### Run the self-check

```bash
python -m infj_bot.core.continuity_vector
```

Drives the three expected baselines (companion → `[1,0,0]`, task → `[1,1,0]`, exploration → `[0,1,1]`) and reports the dominant pattern across them.

---

## When to use which

- **Pre/post ablation comparison, falsifiability proofs, paper-grade numbers** → five-axis vector with stored baselines.
- **Live dashboards, branching logic, "did anything actually change this turn"** → three-axis triad.

Both can run concurrently; they read non-overlapping data and the triad is cheap (six comparisons).

---

## Related docs

- [FALSIFIABILITY.md](FALSIFIABILITY.md) — what claims the five-axis vector supports
- [DMU_PEDI_TEST_PLAN.md](DMU_PEDI_TEST_PLAN.md) — companion test plan for continuity / PEDI
- [SHADOW_GOVERNANCE.md](SHADOW_GOVERNANCE.md) — source of `shadow_influence` for the novelty hook
- [HOW_INFJ_BOT_WORKS.md](HOW_INFJ_BOT_WORKS.md) — broader request lifecycle
