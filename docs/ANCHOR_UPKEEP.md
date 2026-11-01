# Keeping the ANCHOR consumer current

The default branch of infj-bot is `anchor`. CI and Quality must target that branch as well as historical `main` / `master` branches.

`ANCHOR consumer contract` runs on pushes, pull requests, manual dispatch, and daily against the latest ANCHOR `main`. It checks the real knowledge and analytics consumer functions without installing model, voice or vector dependencies. Its JSON artifact records both commit SHAs, the manifest digest, all registered topic digests and the result. Failures remain failures; no dependency installation or repository update is silently substituted for a check.

Run it locally:

```bash
python scripts/check_anchor_contract.py --anchor-root ../ANCHOR --output /tmp/anchor-contract.json
```

A missing checkout or incompatible API exits 1. The daily job detects contract breakage as upstream changes; it does not pull changes into deployed machines, restart MCP, or guarantee semantic freshness of the reference documents. Check the artifact's `anchor_commit` against the deployed checkout when rolling out an update.

Full MCP, model, ChromaDB persistence, voice, and release validation remain separate gates. A green contract check is intentionally narrower than a full application health claim. Existing Quality scan/typecheck commands that use `|| true` remain advisory and should not be treated as enforcing release gates.

The knowledge consumer fingerprints the manifest and provider source on access. Manifest changes rebuild cached topics; provider edits and checkout switches load the exact source from the selected checkout. Existing Markdown topic bodies are read from disk. These refresh rules are regression-tested in `tests/test_anchor_freshness.py`. The source checkout remains operator-controlled trusted code, as it was before this change.

Do not commit local virtual environments or aliases to them. The historical tracked `.venv -> venv` link prevented `python -m venv .venv` from bootstrapping on a clean CI runner; this link is removed. Bootstrap creates a real local environment, which remains ignored.


PR check recovery also removes machine-specific test paths, exports the installed virtualenv launchers through Make, restores the tracked hunt-console HTML, and seeds the SSE test with its own isolated case. Analytics module aliases are restored after use; the sibling checkout is never permanently prepended to the app import path. Python 3.11 is the minimum supported version (the code uses standard-library UTC / StrEnum); CI uses Python 3.12.

Ruff 0.17.3 is pinned to keep this lint/format contract reproducible. The existing selected rules and workflow commands remain enabled. Repository-wide cleanup consists primarily of formatting, annotation/import modernization, explicit subprocess exit handling, and debug traceback logging for optional-runtime fallbacks. Corrected behavioral issues include mutable defaults, blocking I/O in async handlers, and a loop-variable capture in the benchmark. Compatibility exports and historical public filenames retain narrow, documented naming/style exceptions.
