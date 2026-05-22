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
