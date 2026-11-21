# RCCE-1: Strategy-transfer pre-registration (engineering pilot)

Status: **NOT RUN**. This protocol is not evidence of emergent capability or consciousness.
Primary reference: https://zenodo.org/records/20350249
Historical source: DRIFT June 2026 Casual (user-supplied PDF).

## Audited production symbols (master at inspection)
- `core/cognitive_control.py::CognitiveControl.observe(task, strategy, *, outcome, verified)`
- `CognitiveControl.choose(task, candidates) -> Decision`
- `core/cognitive_learning_bridge.py::CognitiveLearningBridge(database, navigator=None, failure_threshold=3)`
- `CognitiveLearningBridge.record(task, strategy, outcome, *, verified, scope='global', evidence='')`
- `CognitiveLearningBridge.choose(task, candidates)`
- Bridge replays SQLite `cognitive_outcomes` into controller at construction; controller indexes outcomes by exact `(task, strategy)` pair.
- Existing test `tests/test_cognitive_learning_bridge.py` covers same-task restart persistence and rejects unverified outcomes, **not cross-task transfer**.

## Gate 0: harness validity
1. Pin commit, model/provider, model parameters, tool access, task set, and randomized run order.
2. Verify real production inference and capture final output after completion; fallback-only or timeout trials are INCONCLUSIVE, not successes.
3. Confirm interventions affect the effective assembled prompt/controller state, not unused background methods.
4. Use isolated persistent stores per condition and record their hashes before and after restart.
5. Never count an asserted `verified=True` as independent validation: evidence must be checked against a deterministic oracle or blind adjudicator.

## Pilot conditions
A. Stateless: no history or adaptive controller.
B. Information-matched: same training facts and token budget, no learned strategy policy.
C. Memory-only: retrieval enabled, controller adaptation disabled.
D. Controller-only: learned strategy policy enabled, relational memory disabled.
E. Full: memory + controller + verified feedback.
F. Fixed replay: same prior history, no interactive feedback.

## Transfer dataset
Use separate training and held-out task IDs and different surface forms. Example principle: after repeated retries fail, inspect the underlying cause and change the method. Training: failing parser test; transfer: failing API schema validation. Neither test should leak the held-out answer.
Include at least 30 held-out problems across multiple families and randomized repetitions. This is a pilot, not a powered confirmatory study.

## Primary endpoint
Binary success on held-out tasks graded by deterministic tests or independent blind adjudicators. Report paired condition differences, uncertainty intervals, trial counts, and failures. Pre-register minimum meaningful effect and confirmatory sample size before running confirmation.

## Causal and persistence checks
- Restart the process and reconstruct the controller from SQLite; verify identical learned decisions on the training task.
- Test transfer to a **different task ID**. Existing exact-task controller has no documented cross-task generalization, so transfer must not be assumed.
- Remove or isolate learned state and repeat; compare with information-matched condition.
- Verify partner specificity using consented, pseudonymous interaction histories with matched exposure.
- Never infer consciousness from improvement, relational language, or self-report.

## Stop conditions
Missing real model execution, contaminated holdout, invalid ablation, failed evidence oracle, or uncontrolled model change => INCONCLUSIVE and nonzero CI status. Do not promote any result to a scientific claim without inspectable traces.
