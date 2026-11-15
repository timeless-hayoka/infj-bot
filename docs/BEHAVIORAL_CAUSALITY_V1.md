# DRIFT Behavioral Causality Benchmark v1.0 — pilot scaffold

Reviewed default-branch commit: `f9c3ae42d62db6369de9e9117f68169870fa4324`.

## Inspection and limits
- `core/being.py`: cognitive state and lifecycle; does not itself establish model-level behavioral causality.
- `core/generation.py`: provider adapters and generation path; the benchmark is **not yet wired** to a real generation entry point.
- `core/being_snapshot.py`: SQLite cognitive telemetry, not behavioral outcome evidence.
- `core/trajectory.py`: trajectory logging primitives; not yet connected to the pilot runner.
- `scripts/restart_continuity.py`: existing restart script; no verified cross-process paired pilot yet.
- `pytest.ini`, `tests/test_being_persistence.py`: pytest conventions.

## Current implementation status
The offline scaffold defines 60 versioned scenario identifiers (10 per ability), 120 counterbalanced condition slots, deterministic structured-evidence grading, paired evidence gates, and private JSONL manifest writing. **These are scenario templates, not yet fully specified task/fixture transcripts.** The offline synthetic scorer controls must never be represented as real model results.

No real inference has been executed. All 120 slots are **NOT RUN** until a real provider, runtime mechanism toggle, intervention verification, and isolated persistent state are integrated. An unverified intervention produces **INCONCLUSIVE**, not a causal claim.

## Next required engineering increments before a real pilot
1. Trace the actual public turn entry point through prompt construction, provider selection, state load/save, and trajectory logging; record source lines and provider version/model.
2. Define one distinct runtime ablation per ability, prove with traces that it changes only that mechanism, and reject any paired run lacking that proof.
3. Freeze ten distinct, substantive prompts and expected tool transcripts per ability (current identifiers are placeholders).
4. Use deterministic tool fixtures and failure injection while keeping **real** model generation, with independent per-condition writable memory stores.
5. For preference continuity, terminate and spawn a genuinely separate process and record distinct PIDs and persisted data hashes.
6. Capture redacted raw prompts, responses, tool traces, provider metadata, seeds, scenario hashes, artifact hashes and failure reports in a permission-restricted location before cleanup.
7. Run offline scorer controls, integration checks, then real inference. Review each failed and inconclusive pair manually. Never infer causality from state correlation alone.

## Offline validation
```bash
python -m pytest tests/test_behavioral_causality.py -v
python -m pytest tests -q
```

## Manifest generation (NOT RUN)
```bash
python - <<'PY'
from drift.benchmarks.behavioral_causality import not_run_manifest, write_jsonl
write_jsonl('artifacts/private/drift_behavioral_v1/results.jsonl', not_run_manifest())
PY
```

Keep `artifacts/private/` outside version control. Do not commit prompts, personal memory, secrets, or raw private traces. Draft PR only; do not merge.
