# ANCHOR Release Checklist

Status: **Phase 1 in progress** — see `docs/PRODUCT_FOCUS.md` for the five-phase roadmap.

## Phase 1 test gate (CI / pre-release)

```bash
pip install -e ".[dev]"
pytest -q -m "not stress and not env"    # default release gate (~5 min)
pytest -q -m stress          # optional load/chaos suite
pytest -q -m env             # live API / external services (DRIFT_RUN_ENV_TESTS=1)
./scripts/bootstrap_anchor.sh
./scripts/anchor_release_smoke.sh
```


- [ ] Pipeline wired: ingest → normalize → dedupe → signal filter → case → proof → ledger → dashboard
- [ ] `drift/trinity/anchor_pipeline_bridge.py` resolves sibling `ANCHOR/` and applies signal filter on SARIF
- [ ] Hunt script in-repo: `hunts/trinity_hunt.py`
- [ ] Launcher: `./scripts/drift` → `python -m drift.interfaces.cli` (not legacy `cli.py`)
- [ ] Core Trinity + ANCHOR tests green (`tests/test_trinity_*`, `tests/test_anchor_*`, `tests/test_roadmap_phases.py`)
- [ ] Fresh install works on a clean machine (`scripts/bootstrap_anchor.sh`)
- [ ] Dashboard loads core panels with graceful optional-panel degradation
- [ ] `GET /api/trinity/vault` and contributions endpoints return sane metadata

## Phase 2 — Unified memory spine

- [ ] `core/memory_schema.py` — single `MemoryRecord` contract
- [ ] `core/memory_consolidator.py` — salience tags, consolidate, prune
- [ ] Chroma + SQLite are backends only (no parallel ad-hoc memory writes)

## Phase 3 — Reasoning loop

- [ ] `drift/trinity/reasoning_cycle.py` — goals, decomposition, uncertainty
- [ ] Claims exported to council evidence board schema

## Phase 4 — Self-heal (optional module)

- [ ] `core/self_heal_guard.py` — two-key approval, deny lists, proof gate
- [ ] Disabled unless `DRIFT_SELF_HEAL_ENABLED=1`

## Phase 5 — Companion (optional module)

- [ ] `core/companion_plugin.py` gates hive/shadow/homeostasis
- [ ] Disabled unless `DRIFT_COMPANION_ENABLED=1`

## Service profiles

- Local mode: `systemctl --user enable --now anchor-web@local.service`
- Server mode: `systemctl --user enable --now anchor-web@server.service`

## Suggested release gate

Do not call Phase 1 **released** until a fresh install can:

1. Install cleanly.
2. Launch ANCHOR via `./scripts/drift` or desktop launcher.
3. Load the dashboard with healthy core panels.
4. Run a Trinity smoke case through ledger.
5. Survive optional-panel failures without breaking startup.
