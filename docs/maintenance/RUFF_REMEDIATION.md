# Ruff backlog: runtime-first remediation

This maintenance track is intentionally separate from RCCE-1 research (PR #46).

## Observed baseline

The Quality workflow on the RCCE-1 branch failed in its repository-wide `ruff check .` step on 2026-11-20. Its output includes F012 (mutable class defaults) and F059 (unused unpacked values), among other findings. The existing Quality workflow also runs `ruff format --check .`, but that step does not execute after a failing Ruff check. The previously reported ~2,652 findings are not a verified count for the master branch.

## Remediation order

1. Generate a machine-readable Ruff baseline from **master**; group by rule and path. Never assume that an ignored diagnostic is safe.
2. Address runtime-risk findings first: syntax and undefined-name failures, mutable class defaults, and any rule with a demonstrable behavioral impact. Review and test each patch individually.
3. Resolve imports and unused values after verifying no side effects or public API changes.
4. Handle formatting-only changes separately; do not mix mass formatting with functional repairs.
5. Require relevant pytest regression coverage and a scoped Ruff check before merging each batch. Preserve the existing repository-wide Quality check and its failure visibility; do not blanket-ignore diagnostics or claim success until it passes.

## Status

This first commit documents the isolated remediation track; **no Ruff defects have yet been repaired**. Future changes should cite affected files, rule IDs, tests, and before/after counts.
