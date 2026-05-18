# Elysium Phase 5 — File Index

All paths are relative to `infj_bot/` (the project root).

## Core Elysium Files (new)

| File | What it does |
|------|-------------|
| `core/hive/__init__.py` | Exports: `get_elysium()`, `get_nexus()`, `CouncilMember`, `CouncilRole` |
| `core/hive/elysium.py` | **Main engine.** Runs the Nexus Loop: decide(), reflect(), council_status(). |
| `core/hive/nexus.py` | **Persistent self-model.** Goals, moral stance, narrative arc, tension tracking, coherence. |
| `core/hive/council_member.py` | **7 persistent voices.** Memory-view filters, proposals, critiques, energy, win tracking. |
| `core/hive/INDEX.md` | This file. |

## Files Modified for Elysium Wiring

| File | What changed |
|------|-------------|
| `core/commands.py` | Added `/hive nexus decide`, `/hive reflect`, `/hive council status` handlers. |
| `main.py` | Imports `get_elysium`; health check; background reflection every 25 loops; known modules. |
| `CHANGELOG.md` | Elysium Phase 5 entry. |
| `docs/HIVE_ROADMAP.md` | Phase 2 marked shipped; Phase 5 Elysium added. |

## Tests

| File | What it covers |
|------|---------------|
| `tests/test_elysium.py` | 10 tests: Nexus roundtrip, decision integration, tension resolution, council proposals, critiques, memory filters, council container, Elysium decide/reflect/status. |

## Related Existing Files (good to know)

| File | Why it matters |
|------|---------------|
| `core/memory_spine.py` | DMU memory engine that Elysium pulls from during Ignition. |
| `core/phi_council.py` | Original Council of 7 mapping (Aura→emotional_field, Logic→cognition, etc.). |
| `core/cognitive_architecture.py` | Plugin registry, `CycleContext`, consciousness loop orchestration. |
| `hive_mind/orchestrator.py` | Existing HiveOrchestrator (node registry, heartbeat, consensus engine). |
| `hive_mind/consensus_engine.py` | Weighted voting, thread resolution used by `/hive propose`. |

## Quick Commands

```bash
# Run only Elysium tests
cd /home/crexs/infj_bot
./venv/bin/pytest tests/test_elysium.py -v

# Run full suite (skip known-broken collectors)
./venv/bin/pytest tests/ -q --ignore=tests/test_bot.py --ignore=tests/test_evaluators.py --ignore=tests/test_growth_trajectory.py --ignore=tests/test_shadow.py
```

## Database Files (runtime, SQLite)

These are created automatically on first run:

- `data/nexus.db` — Nexus self-model state, decisions, reflections
- `data/council.db` — Council member states, proposals, critiques
- `data/elysium.db` — Deliberation history, reflection log
