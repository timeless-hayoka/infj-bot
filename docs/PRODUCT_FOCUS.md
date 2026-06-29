# ANCHOR Product Focus

**Core product:** ANCHOR — evidence-before-belief proof-gated security findings.

Everything else (companion personality, self-heal, cloud templates, research harnesses) ships as **optional modules** after the spine is solid.

## Phase 1 — ANCHOR engine (primary)

**Pipeline:** ingest → normalize → dedupe → signal filter → case → proof → ledger → dashboard

| Stage | Module |
|-------|--------|
| Ingest | `drift/trinity/caseflow.py`, SARIF/Slither/Foundry adapters |
| Normalize / dedupe / signal filter | `drift/trinity/anchor_pipeline_bridge.py` → `ANCHOR/anchor_sarif` |
| Case / proof | `drift/trinity/council/` (EvidenceBoard, CouncilRunner) |
| Ledger | `TrinityCaseLedger` in caseflow |
| Dashboard | `interfaces/api.py`, anchor analytics panels |
| Hunts | `hunts/trinity_hunt.py` |
| CLI | `scripts/drift` → `python -m drift.interfaces.cli` |

**Release gate:** `docs/ANCHOR_RELEASE_CHECKLIST.md`

## Phase 2 — Unified memory spine

One schema (`core/memory_schema.py`), salience tags, consolidation, conflict resolution, scheduled prune (`core/memory_consolidator.py`).

Vector (Chroma) and episodic (SQLite) are **backends** of the spine — not parallel memory systems.

## Phase 3 — Reasoning loop

Structured goals, decomposition, uncertainty on claims (`drift/trinity/reasoning_cycle.py`), wired to the council evidence board schema — not freeform chat magic.

## Phase 4 — Hardened self-heal (optional module)

Two-key patch approval, deny lists, rollback artifacts, never bypass proof gate (`core/self_heal_guard.py`).

## Phase 5 — Companion / personality (optional module)

Hive, shadow, homeostasis gated behind `core/companion_plugin.py` — off by default for ANCHOR deployments.

## Environment

| Variable | Purpose |
|----------|---------|
| `ANCHOR_ROOT` | Path to sibling `ANCHOR/` repo (default: `../ANCHOR` from infj_bot) |
| `DRIFT_COMPANION_ENABLED` | `1` to enable Phase 5 companion modules |
| `DRIFT_SELF_HEAL_ENABLED` | `1` to enable Phase 4 (still requires two-key approval) |
