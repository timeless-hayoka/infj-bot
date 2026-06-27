# ANCHOR Case Study Template

Use this template for every finding, benchmark result, or public case study.

## Title

`[Finding name] in [target]`

## One-line summary

`[What was discovered, where, and why it matters.]`

## Context

- Product or repository:
- Run or benchmark id:
- Date:
- Environment:
- Scope / authorization note:
- Tooling used:

## Signal

Describe the first meaningful signal.

- Tool or source of signal:
- What it reported:
- Why it looked suspicious:
- Initial confidence level:

## Evidence

List the evidence that supported the signal.

- Logs:
- Screenshots / traces:
- Score decomposition:
- Relevant metadata:
- Artifacts preserved:

## Failed Attempts

Show what did not work before the proof landed.

1. Attempt:
2. Outcome:
3. Why it failed:
4. What was learned:

## Successful Reproduction

Describe the exact path to a confirmed reproduction.

- Target component:
- Steps taken:
- Proof-of-concept or test used:
- Result:
- Verification level:

## Impact

Explain the practical consequence.

- Security impact:
- User or system impact:
- Scope of affected surface:
- Confidence in impact assessment:

## Remediation

State the fix clearly.

- Recommended fix:
- Defense-in-depth improvement:
- Follow-up validation:
- Residual risk:

## Lessons Learned

- What the signal got right:
- What the system missed initially:
- What improved after the rerun:
- What to change in future evaluations:

## Public Summary

`Signal -> evidence -> failed attempts -> successful reproduction -> remediation`

## Artifacts

- Case file:
- Score trace:
- PoC / test:
- Regression test:
- Related benchmark run:
- Notes:
