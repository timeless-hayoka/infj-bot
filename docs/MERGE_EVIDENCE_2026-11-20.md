# DRIFT merge evidence — 2026-11-20

This document is the review index for the `local-continuity` branch at
`df89a1c` plus the final merge-readiness fixes. It records what was tested,
what the research demonstrates, and what is deliberately not claimed.

## Scope under review

The branch adds and hardens:

- local restart-continuity evaluation with isolated ON/OFF conditions;
- memory facts, persistence, rollback, and prompt-budget safeguards;
- bounded API readiness and side-effect-free liveness checks;
- local CLI and virtual-environment discovery;
- local mouse-automation safety checks;
- development, security, and repair regression coverage;
- container and CI configuration hardening.

The implementation and detailed continuity methodology are in
[`local-restart-evaluation.md`](local-restart-evaluation.md). The branch commit
changes 44 files with 3,655 insertions and 385 deletions.

## Reproducible verification

All commands below were run from `/home/jude/Projects/infj-bot` on Linux with
Python 3.14.10.

| Gate | Command | Result |
|---|---|---|
| Full validation | `bash run_full_test_suite.sh` | PASS: provenance, syntax, dependencies, and pytest |
| Full pytest | `.venv/bin/python -m pytest tests/ -q --tb=short` | **449 passed, 6 skipped, 1 expected warning** |
| Target merge simulation | Merge into `origin/anchor@299fbec` in a disposable worktree, then run full pytest | **Clean merge; 471 passed, 6 skipped, 1 expected warning** |
| Offline release gate | `./scripts/run_release_tests.sh` | **421 passed, 2 skipped, 32 deselected; CLI gate passed** |
| Dashboard/API smoke | `./scripts/anchor_release_smoke.sh` | **dashboard smoke OK; release smoke complete** |
| Ruff | `ruff check` and `ruff format --check` on the merge surface | PASS |
| Type checking | CI mypy command over five maintained core modules | PASS |
| Security | Bandit high-severity scan of tracked Python | PASS |
| Secrets | `detect-secrets-hook --baseline .secrets.baseline` on tracked files | PASS |
| Runtime status | `./scripts/drift status --json` | healthy; doctor status `ok` |

The full validation evidence was generated at
`logs/validation-20261120T072501Z/`. Validation directories are intentionally
runtime artifacts; the stable counts and commands are retained here.

### Regression evidence

- Before isolating readiness globals, the full suite produced **447 passed,
  6 skipped, 2 failed**. Both failures passed alone, proving order-dependent
  state leakage. Resetting `memory` and readiness coordination state in those
  tests produced the final 449-pass run without changing production behavior.
- The CLI module regression test promotes `RuntimeWarning` to an error. It
  fails with the former eager package import and passes with lazy compatibility
  exports. The release smoke no longer emits the `runpy` warning.

## Research and evaluation map

### Merge-visible research

- [`local-restart-evaluation.md`](local-restart-evaluation.md) defines the
  restart-continuity protocol, controls, scoring, raw-artifact layout, and
  limitations.
- `scripts/local_continuity.py`, `scripts/restart_continuity.py`, and
  `scripts/continuity_system_prompt.txt` implement the protocol.
- `tests/test_local_continuity.py` verifies scoring, scenario construction,
  prompt capture, isolation, and persistence rules.

### Local experimental evidence

These files remain outside the merge because they are generated or form a
separate research workstream:

- `results/alder-smoke/`: one real local-model comparison pair. Continuity ON
  scored 6/7 and OFF scored 1/7, a paired difference of +5. This is promising
  integration evidence, not a representative benchmark.
- `results/alder-smoke-20261118/`: a later local llama.cpp run with model and
  harness provenance.
- `break_it_report_*.md` and `break_it_results_*.json`: six negative cognitive
  load experiments. All failed; several measure provider/server unavailability
  or timeout rather than reasoning quality. They are retained as honest
  failure evidence and are not presented as a passing benchmark.
- `grants/`: grant discovery, shortlists, and draft worksheets. This research
  is useful for funding work but is unrelated to the runtime merge and has its
  own source-freshness and lint review requirements.

## Known limitations and deliberate exclusions

- The full suite skips six environment-dependent checks. No claim is made for
  paid model providers, external vault mounts, or unavailable live services.
- Stress, Docker, Foundry, and hardware-specific validation were not rerun in
  this local merge-readiness pass; their hosted workflows remain the authority.
- Pytest emits one intentional low-variance warning from a test that verifies
  the warning path. It must be resolved before interpreting a real ablation
  dataset with near-zero variance.
- The editable-install build advisory is a setuptools development-mode notice,
  not an application failure.
- One Alder pair is insufficient for a general scientific conclusion. Run the
  documented 20-pair evaluation before making population-level claims.

## Operational readiness and rollback

- `./scripts/drift status --json` reports healthy launchers, virtualenv,
  modules, database, archive smoke, and export smoke.
- The API liveness route avoids slow dependency initialization; readiness uses
  a bounded daemon initializer and returns `503` on timeout or failure.
- Rollback is a normal Git revert of the merge commits. No schema migration or
  irreversible external write is required by this change set.
- Local test state uses temporary `DRIFT_OS_ROOT` storage. Generated logs and
  research outputs are not required to run the application.

## Readiness decision

**Ready with evidence for code review and merge**, subject to hosted CI passing
on the final commits. A dry merge into the current `origin/anchor` completed
without conflicts and its full pytest suite passed. Live-provider, stress,
Docker, Foundry, and a full 20-pair continuity experiment remain separate
validation claims.
