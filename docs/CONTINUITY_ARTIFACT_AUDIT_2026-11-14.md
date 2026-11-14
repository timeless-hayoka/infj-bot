# Continuity evaluation audit — 2026-11-14

Source: seven JSON artifacts supplied by the project owner. This report is **not** a reproduction of live model inference. Raw model outputs and per-pair grading records were not included.

## Reconciled results

- 20 distinct project scenarios, seven fields per scenario; 140 scored fields per condition.
- Memory ON: 71/140 = 50.71%; OFF: 23/140 = 16.43%; paired total difference +48 fields.
- The reviewer field is null in all 20 expected answers and both conditions score 20/20. For the six informative fields: ON 51/120 = 42.5%; OFF 3/120 = 2.5%.
- Preference: ON 0/20; OFF 0/20.
- Current delivery day after supersession: ON 4/20; OFF 0/20.
- Completed step: ON 6/20; OFF 0/20. Next step: ON 6/20; OFF 0/20.
- All-seven-correct: 0/20 in both conditions.
- The two supplied scoring-rules files are byte-identical; audit.json's summary matches summary.json.
- Midpoint audit reports 10/20 pairs, 140 calls; final audit reports 20/20 pairs, 280 calls.

## Interpretation and limitations

These artifacts support a *reported* ON-vs-OFF difference for a local Qwen2.5 0.5B quantized model. The uploaded audit claims real inference, unchanged model digest, no response cache, identical primary system prompt hashes, and matched settings. These are **assertions in the audit**, not independently proven by the aggregate files. No raw answers, full prompts, trace of retrieval selection, per-pair scores, execution logs, or harness source were supplied; independent response-level rescoring and end-to-end reproduction are impossible with this package.

The setup sentences include project-specific preferences, superseded delivery dates, and ordered task progress. Thus preference, supersession and next-step failures are important, but the artifacts alone cannot isolate retrieval failure from prompt trimming, model comprehension, or scorer normalization. Reviewer abstention accuracy is a weak discriminant because all expected values are null.

## Repository observations

- `adapters/memory_adapter.py:MemoryAdapter.query_all` currently returns `Not implemented` for working, semantic, and shared layers. This is a separate verified placeholder; the uploaded evaluation does **not** establish that this adapter was exercised.
- `core/plugins/preferences.py:PreferenceStore` persists structured preferences and promoted directives, but does not itself establish that natural-language project preferences in ordinary chat are extracted and promoted.
- `scripts/restart_continuity.py` uses a mocked provider in its offline probe; passing it cannot establish live-model answer accuracy.
- The local evaluation metadata names `scripts/local_continuity.py` and a system prompt at a local path, but that harness was not found in the GitHub default branch during this audit. Obtain its exact committed source and raw responses before treating the report as independently reproducible.

## Next implementation gates

1. Export anonymized per-pair raw responses, prompt hashes, retrieval IDs/ranks, normalized fields, and scorer version; do not export private user data or secrets.
2. Run evaluator against the exact uploaded artifacts using `python scripts/audit_continuity_artifacts.py PATH` and unit tests with `pytest -q tests/test_continuity_artifact_audit.py`.
3. Add end-to-end regression tests for project-scoped preference extraction/promotion/retrieval, newest-date supersession, and ordered task-state reconstruction. Keep scorer correctness separate from retrieval recall and answer correctness.
4. Measure per-field precision, recall, false assertions, abstentions, and paired confidence intervals across multiple models and seeds. Include context budget ablations and no-memory controls.
5. Do not claim 95% memory accuracy, real-world retention improvements, or verified security resilience based on these 20 scenarios.
