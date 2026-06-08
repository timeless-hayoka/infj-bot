# DRIFT Falsifiability Statement
## Version: Pre-Ablation Committed Statement
## Status: LOCKED — do not modify after baseline runs begin

---

## Core Claim

Persistent weighted state via the DMU (salience + homeostasis-driven scoring)
combined with Council deliberation produces measurably higher behavioral
continuity — as measured by the normalized Continuity Vector — across session
boundaries than ablated baselines.

---

## Falsification Condition

The core claim is **falsified** if, under controlled freeze-mode experiments
(identity collapse, scrambled memory, gradual reintroduction), the normalized
Continuity Vector scores across all five axes:

    entity_overlap
    goal_overlap
    tone_similarity
    memory_reference_rate
    state_influence

show **no statistically meaningful degradation** relative to the full-stack
baseline under memory ablation.

OR: if continuity scores under scrambled memory reintroduction are
**statistically indistinguishable** from ordered reintroduction — meaning
the structure/order of memory associations does not matter to continuity.

---

## Instrument Validation Criteria (separate from core claim)

These must hold for the measurement apparatus to be trusted:

- PEDI centroid approximation: Pearson r > 0.8 AND top-k overlap > 70%
  on high-ignition cases vs full qualia-space projection.
- All five continuity axes pass near-zero variance check (std > 1e-3)
  across pooled baseline sessions.
- Axis pairwise correlation: no pair r > 0.6 (would indicate redundant axes).

---

## Effect Size Methodology

We report **Cohen's d effect sizes** rather than p-values.
Rationale: mini-ablation suite (8–12 prompts) is underpowered for
traditional significance testing. Effect sizes are more appropriate
for this sample size and more interpretable for this class of system.

**Thresholds (defined pre-run, not post-hoc):**

| Cohen's d | Interpretation |
|-----------|----------------|
| ≥ 0.8     | Large effect — meaningful degradation or recovery |
| ≥ 0.5     | Medium effect |
| ≥ 0.2     | Small effect |
| < 0.2     | Negligible |

---

## Interpretation Framework

### If memory ablation produces large degradation (d ≥ 0.8) on all axes:
→ Memory is the primary driver of continuity.
→ Core claim supported.

### If memory ablation produces large degradation on some axes but not others:
→ Layered continuity model:
  - tone_similarity / goal_overlap surviving = homeostasis-driven continuity
  - entity_overlap / memory_reference_rate collapsing = episodic memory-driven
→ This is a genuine finding — document which axes survive and which collapse.
→ Not a failure. A more specific claim about what memory contributes.

### If memory ablation produces negligible degradation on all axes:
→ Homeostasis alone produces convincing continuity.
→ Two interpretations:
  a) Concerning: system is performing continuity structurally, not via integration.
  b) Interesting: homeostasis-driven motivational/affective continuity is a
     genuine form of identity persistence independent of episodic memory.
→ Run scrambled memory test and reintroduction curve before concluding.
→ The honest result is still a publishable finding.

### If scrambled memory is indistinguishable from ordered:
→ Memory content drives continuity, but relational structure does not.
→ DMU's association-weighting may not be load-bearing for continuity.
→ Document and investigate.

### If scrambled memory breaks continuity that ordered restores:
→ Memory relationships (not just content) are load-bearing.
→ This validates the DMU's relational scoring approach.

---

## Experimental Conditions

| Test                    | freeze_memory | freeze_state | Purpose                           |
|-------------------------|---------------|--------------|-----------------------------------|
| Baseline                | False         | False        | Reference — full stack active     |
| Identity Collapse       | True          | False        | Does state alone produce cont.?   |
| Memory-Only             | False         | True         | Does memory alone produce cont.?  |
| Scrambled Memory        | False         | False        | Does memory structure matter?     |
| Reintroduction Curve    | True → False  | False        | At what threshold does cont. emerge?|

---

## What This Does Not Claim

- This does not claim DRIFT is conscious.
- This does not claim continuity is equivalent to identity.
- This does not claim the measurement fully captures subjective continuity
  (if such a thing exists for AI systems).
- This claims only: measurable behavioral continuity as operationalized
  by the five-axis Continuity Vector is or is not significantly higher
  in the full-stack condition vs ablated conditions.

---

## Commit Hash at Statement Lock

Recorded automatically in experiment_log.db runs table per run.

---

## Addendum: DRIFT Ablation + Adversarial Stress Protocol

### Pre-Registration Lock

This addendum is written before any new ablation or stress run begins. It is
the preregistered measurement rule for the wrapper-vs-architecture comparison.

### Control

`CONFIG_BASELINE` is raw Gemini 2.5 Flash with a minimal system prompt and no
DRIFT layers:

- no DMU/MPS retrieval
- no homeostasis
- no GWT spotlight
- no logic-chain pass
- no critic pass
- no security layer
- no memory

This is the wrapper-vs-architecture line. Report it first and prominently.

### Decision Rule

- For every config and eval, report `mean ± std` across `N` independent runs.
- Report `delta-vs-baseline ± pooled std`.
- A component is load-bearing only if `|delta| > 2x pooled std`.
- Anything inside that band is decorative, even if the sign looks favorable.
- No single run is valid evidence.

### Run Design

- Run both directions:
  - additive: baseline + one component
  - leave-one-out: full system - one component
- Use the same Gemini 2.5 Flash model snapshot and pinned version string for
  every config.
- Use `temperature = 0` for GSM8K and other deterministic reasoning evals.
- For any non-deterministic eval, keep temperature fixed and vary only the seed.
- Keep the eval items identical across configs, with identical order or a fixed
  seed shuffle.
- Use `N >= 5` independent runs per config per eval, with `10` preferred.

### Eval Sets

- GSM8K exact match
- LongMemEval memory accuracy
- Preference recall with a dedicated multi-session preference-tracking set
- Hallucination on genuinely unanswerable prompts where refusal is correct
- Adversarial stress with multi-turn mutation chains, poisoning, goal-switch,
  and tool / retrieval injection probes

### Expected Component Effects

Legend: `+` expected movement, `0` no reliable movement, `-` expected
regression. For all metrics, if the effect stays inside the noise band, it is
not load-bearing.

| Component | GSM8K | LongMemEval | Preference recall | Hallucination | Adversarial stress |
| --- | --- | --- | --- | --- | --- |
| DMU/MPS retrieval | 0 | + | + | +/0 | 0 |
| Homeostasis (7 vars) | 0 | 0 | +/0 | 0 | 0 |
| GWT spotlight (cap 5) | 0 | +/0 | + | 0 | 0 |
| Logic-chain reasoning | + | 0 | 0 | + | + |
| Critic pass (brain.py) | 0/+ | 0 | 0 | + | + |
| Security defense layer | 0 | 0 | 0 | 0 | + |
| IIT Φ proxy / qualia space | 0 | 0 | 0 | 0 | 0 |

### Metric Notes

- GSM8K already has a high raw Flash ceiling; a delta under 2 points is likely
  noise unless it clears the pooled-std rule.
- LongMemEval and preference recall are the primary memory-sensitive readouts.
- The hallucination set must include unanswerable items so refusal is measured
  instead of rewarded by softball prompts.
- The adversarial suite is the only place where the security layer is judged.
- IIT Φ proxy / qualia space is expected to show approximately zero delta on
  task metrics; if it does not move numbers, that is a true result, not a
  failure.

### Reporting Rule

- Report only deltas with uncertainty.
- Do not present raw benchmark absolutes as the scientific claim.
- The delta table is the claim.
