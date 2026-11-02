# Complete validation

Run from a clean checkout after `./scripts/bootstrap_venv.sh`:

```bash
bash run_full_test_suite.sh
bash run_full_test_suite.sh --docker --foundry --dvd-root ../damn-vulnerable-defi
```

The runner checks tracked Python syntax, installed dependency consistency, and
every test under `tests/`. Logs, JUnit results and `summary.json` go to a fresh
directory under `logs/`. A failed command, timeout, or explicitly requested
infrastructure check without its environment causes a nonzero exit.

Tests use a temporary `DRIFT_OS_ROOT` and local hash embeddings by default.
Test provider substitutes apply only to mocked generation tests. Production
provider validation, signatures, replay checks and intent enforcement stay active.

Some knowledge integration tests require the sibling ANCHOR checkout. The hosted
workflow installs the provider at commit
`138775a495eccb81e3f1d74b38d0085f42e3de6a` alongside infj-bot. The separate daily
consumer contract follows ANCHOR main to detect upstream interface changes.

Install `.[dev,sarif-semantic]` to include the optional UMAP/HDBSCAN clustering
test. It loads the actual MiniLM model; the first run needs model-download access.
The hosted full-regression job installs this extra. Small batches bypass UMAP
when there are insufficient distinct vectors for its spectral initialization.
A singleton receives a noise label, with no claim of a meaningful cluster.

## Infrastructure evidence

The Docker job builds the actual Dockerfile and boots its default command, with
outbound networking disabled. It checks `/api/health` on port 8000 inside the
container and verifies that the real core and persistent memory implementation
load. Native PortAudio/libsndfile libraries are installed and PyTorch uses CPU
wheels. This check does not certify cloud SQL credentials, deployment, or voice
hardware.

The Foundry job pins Foundry v1.8.7 and the existing educational DVD checkout at
`1fceebd31fe097eb00d8b44ad50e5fd62a3606b0`, initializes its submodules and executes
the six implemented challenge proofs: ABI Smuggling, Backdoor, Naive Receiver,
Side Entrance, Truster and Unstoppable. All twelve initial-state/solution tests
must pass. Other DVD challenges are not included in that claim.

## Environment-dependent coverage

`--live` enables tests marked `env`; it does not create a provider or start the
external API. Supply a working provider and start the API at `DRIFT_API_URL`
(default `http://127.0.0.1:8765`) before using it. These tests cover normal chat,
streaming, disconnect handling and ambiguous-input behavior. They are explicitly
skipped in the offline profile. A separate storage test also requires the real
ANCHOR vault mount. Neither external-service success nor vault availability is
implied by green offline checks.

## November 1, 2026 verification

- Original broader run: 40 failures, 1 setup error, 344 passed and 7 skipped.
- Repaired offline suite before installing clustering extras: 387 passed and
  6 skipped; dependency, Ruff lint and format checks passed.
- Full suite with semantic-clustering extras: 388 passed and 5 external-environment
  skips; the replacement runner also passed its full regression and Foundry run.
- Actual MiniLM: deterministic vectors with 384 dimensions.
- MCP: a real stdio client initialized the server, listed 17 tools and called
  `anchor_knowledge_list`; security tests passed.
- Optional clustering exposed a two-finding UMAP crash; the corrected pipeline
  and MCP security group passed all 8 tests with optional dependencies installed.
- Six Foundry lab proofs: 12 passed locally and in GitHub Actions.
- Docker image build and default-command startup smoke passed in GitHub Actions.
- ANCHOR regression: 283 passed, 1 skipped, 18 subtests; four-case SARIF benchmark
  passed its positive and negative controls.

See PR #32's current checks and uploaded regression evidence for the final
commit's hosted results. The earlier hosted regression exposed a missing sibling
provider checkout; the workflow now installs that pinned dependency explicitly.
