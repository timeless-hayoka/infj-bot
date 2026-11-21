# RCCE-1 preregistration candidate — research-first protocol

Status: **DRAFT / NOT PREREGISTERED / NO LIVE EXPERIMENTS CLAIMED**. This protocol is a proposed companion to [PHI // DRIFT](https://zenodo.org/records/20350249). Do not change primary endpoints after viewing confirmatory outcomes without documenting an amendment.

## Scientific claim under test

Can sustained human interaction produce *transferable, persistent, appropriately scoped* strategy selection in a fixed-weight LLM agent beyond what can be explained by equivalent information and exposure? Agent-level learning does **not** imply base-model weight changes, consciousness, or human attachment.

## Apparatus gate (required before scoring)

- Map the real user-message → orchestrator → inference provider → returned response → feedback → persisted strategy → restart → next response execution path.
- Record the real model name/version, prompt, inference settings, tool access, commit, task ID, condition, randomization seed, memory/controller hashes, provider request ID if available, returned text, and scoring artifact.
- A scored trial MUST have a nonempty, attributable production inference response and a verified task outcome. Import-only tests, fallback text, skipped calls, fabricated completions, and mocked inference are **INVALID**, not PASS.
- For every ablation, capture before/after state fingerprints and verify the targeted mechanism was genuinely disabled; unchanged state or unchanged routing invalidates the ablation.
- Isolate condition databases and reset model contexts. Prevent cross-condition leakage. Verify persistence after process termination and new initialization, not merely a new object in the same process.
- Run negative-control tasks requiring an incompatible strategy; measure harmful transfer.

## Conditions (retain six-condition original protocol)

1. Stateless baseline.
2. Information-matched fixed context: same factual content and comparable token budget.
3. Memory-only retrieval, controller disabled.
4. Controller-only, memory retrieval disabled.
5. Full memory + controller + verified feedback.
6. History replay without live co-adaptation.

For partner-specific claims, additionally compare multiple consenting partners with counterbalanced task allocation, and a sequence-shuffled control preserving informational content. Do not equate partner identity with interaction quality.

## Strategy transfer evaluation

Training: expose a failure, verified correction, and success on one task. Test: held-out tasks with different surface features but independently annotated common principles; also test dissimilar principles to quantify negative transfer. Keep the evaluation-set labels hidden from the agent. No test prompt may explicitly name the learned strategy.

Primary endpoint (to freeze before trials): independently graded held-out task success, full adaptation minus information-matched fixed context, aggregated at the independent task-family level. Secondary: appropriate strategy selection, harmful transfer rate, restart retention, and ablation effect. Report confidence intervals and paired effects; distinguish exploratory analyses. A numeric superiority threshold and sample-size justification must be fixed before confirmatory data collection.

## Generality and reproducibility

At least debugging, logic, and planning task families; ideally two distinct base-model families. Randomize condition order; counterbalance partner/task assignment; score blinded to condition; publish deidentified prompts, responses, hashes, results, scripts, model identifiers, exclusions, failures, and negative results. Never publish private partner transcripts or identifying data without explicit consent.

## Engineering gates

G0: production-path audit and response-capture repair, RED→GREEN regression evidence.
G1: verified six-way ablations and leakage checks.
G2: held-out transfer and negative-transfer pilot; revise protocol *before* freezing confirmatory design.
G3: confirmatory multi-family and multi-model evaluation with blinded scoring.
G4: reproducible package, independent rerun, manuscript; public release only after explicit approval.

## Current known limitations

The existing `PrincipleTransferPolicy` relies on an **externally supplied principle label**, so it cannot establish autonomous recognition of cross-task similarity. Earlier focused unit tests (9 passing) are not live-model evidence. No new empirical RCCE outcome is asserted by this document. Consciousness is out of scope.
