# DRIFT math and preference hardening

## Runtime boundary

`core/safe_math.py` interprets an explicit Python AST allowlist. Arithmetic uses
`Fraction`, preserving the actual source spelling of decimal literals. It rejects
non-finite values, oversized expressions/results, variable exponents, deep trees,
large powers, attributes, subscripts, arbitrary calls and keyword arguments.
Resource rejections do not fall through to a less restrictive evaluator.

Symbolic requests run in `core/_safe_math_worker.py`, a fresh isolated Python
process. Both the parent and worker validate the actual normalized expression.
The worker builds SymPy objects from that AST with explicit constructors; it does
not use `eval`, `sympify` or `parse_expr` on input text. SymPy is pinned to 1.14.0.

The worker sets hard limits **before importing SymPy**: 2 CPU seconds, 512 MiB
address space, 16 MiB stack, 32 descriptors, zero file output and no core dumps.
The parent allows at most four simultaneous symbolic workers per process and
kills/reaps a timed-out worker's process group after three wall-clock seconds.
Unsupported platforms and worker/setup failures fail closed. These limits contain
resource use; they are not a sandbox for executing arbitrary Python code. The
security boundary is the validated AST and explicit constructor interpreter.

Grounding renders symbolic values and checks whole numerical values rather than
substrings (`1` inside `10` cannot satisfy the check). Final non-streaming critic
output is checked, and streaming paths append any missing verified correction at
completion. Already emitted stream text cannot be retracted. This is a consistency
check, not a proof that all numbers in arbitrary prose are correct. Expression
extraction remains conservative and unsupported queries can be refused.

## Preference read path

`PreferenceStore.promote_preference` atomically replaces the stored value and its
promotion marker. `get_promoted_directives` reads current directives from SQLite.
Prompt formatting reads the preference values and promotion flags in one query,
avoiding an inconsistent snapshot across concurrent reads. Legacy `output_style`
setters still produce their directive.

The stress harness uses the real `PreferenceStore`, `BotState`, `DriftMemory`
(with the repository's deterministic local embeddings), `CognitiveOrchestrator`
and assembled prompt. It changes a preference, checks the current directive is
present, and checks all superseded directives are absent, including when a value
is selected again. It does not use model inference or a fake assembler.

The CLI sets an isolated temporary `DRIFT_OS_ROOT` **before application imports**
and uses throwaway preference/memory databases. Importing `exercise` directly is
for isolated test processes only (pytest's conftest provides that isolation).
Existing production state must never be passed to this harness.

```sh
python -m pytest tests/test_safe_math.py tests/test_math_grounding.py tests/test_preference_stress.py -q
python tests/preference_stress_runner.py --selftest --cycles 20 --output-dir logs/preference-proof
python tests/preference_stress_runner.py --plant-stale --cycles 1 --output-dir logs/preference-negative
```

The last command must exit **1**. Ordinary runs exit 0 only on PASS; setup errors
are INCONCLUSIVE and exit 2. `--selftest` requires a correct real run to PASS and a
real orchestrator wrapped with a planted stale-directive leak to FAIL. This is a
controlled mutation test, not a claim of model compliance or a live production
failure. The default is 100 turns per run.

Each turn writes a JSONL state trajectory with actual isolated-state energy,
mode, prompt length, CPU/wall timing, the current directive, stale hits and a prompt
diff. No provider call is made; inference CPU is consequently `null`. The existing
runtime homeostasis policy uses inference CPU (or remote-call cost), not wall time.
Full-validation CI preserves these traces and result JSON alongside test evidence.

## Verification limits

Unit tests force a worker timeout and confirm it is reaped, inspect the actual
hard limits at the SymPy operation seam, force a CPU loop to be killed, and refuse
a 1 GiB allocation. Symbolic input is tested again by sending an invalid payload
directly to the worker. The original 18 adversarial examples remain in the suite,
along with symbolic fallback, non-finite, target-variable and syntax regressions.

Live model/API behavior requires a separate provider-backed test. The standalone
harness proves persistence-to-prompt freshness, not natural-language preference
extraction or the model's obedience. The complete local suite also includes a
semantic-model test and environment-dependent API checks; report their actual
availability/results separately rather than treating skipped tests as passes.
