# Hive Mind — Distributed Cognition Package

This page documents the `hive_mind/` Python package: the **public, in-process consensus layer** that backs `/hive propose` and the `GET /api/hive` endpoint. It is intentionally small and dependency-free so that a single-node DRIFT install still works when the rest of the hive is offline.

For the **deeper async council** (Nexus, Elysium, 7 persistent voices) see [`core/hive/INDEX.md`](../core/hive/INDEX.md). The two layers are **separate** — `hive_mind/` is the lightweight thread/voting engine; `core/hive/` is the deliberation engine that uses it.

For the long-term direction across multiple phases see [HIVE_ROADMAP.md](HIVE_ROADMAP.md).

---

## What it is

```
hive_mind/
├── __init__.py            # re-exports the 5 public symbols
├── consensus_engine.py    # ConsensusEngine: propose → vote → resolve
├── orchestrator.py        # HiveOrchestrator: node registry & heartbeat
└── protocol/
    ├── __init__.py
    └── dcp.py             # DCPMessage, NodeRole, Resolution
```

`hive_mind/__init__.py` exports exactly five symbols:

```python
from infj_bot.hive_mind import (
    ConsensusEngine,
    HiveOrchestrator,
    DCPMessage,
    NodeRole,
    Resolution,
)
```

Anything outside this list is implementation detail and may change without notice.

---

## Distributed Cognition Protocol (`protocol/dcp.py`)

The DCP defines the wire format for thoughts that cross node boundaries. Every message is a `DCPMessage` with a short `message_id` (8-char UUID prefix) and an ISO timestamp.

### `DCPMessage`

| Field | Type | Default | Notes |
|-------|------|---------|-------|
| `source_node` | `str` | required | Logical node id (`"spark-0"`, `"lantern-4"`, etc.) |
| `source_role` | `NodeRole` | required | PRIMARY / CRITIC / BACKUP / OBSERVER |
| `content` | `str` | required | Free-form text payload |
| `name` | `str` | `"thought"` | Message kind label |
| `priority` | `float` | `0.5` | Caller-assigned salience hint |
| `payload` | `dict` | `{}` | Arbitrary structured side-data |
| `message_id` | `str` | auto | First 8 chars of a UUID |
| `timestamp` | `str` | auto | `datetime.now().isoformat()` |

Convenience constructor for the common case:

```python
msg = DCPMessage.thought(
    source_node="spark-0",
    source_role=NodeRole.PRIMARY,
    content="What if we cached vector lookups?",
    priority=0.7,
)
```

### `NodeRole`

```
PRIMARY   — proposer / synthesizer
CRITIC    — challenges, looks for failure modes
BACKUP    — redundant primary that can take over
OBSERVER  — read-only telemetry / safety watcher
```

### `Resolution`

Threads close with exactly one of:

```
ADOPTED    — final position accepted
TABLED     — set aside (used for safety vetoes)
REJECTED   — explicitly turned down
PENDING    — still open / waiting for more data
```

---

## `HiveOrchestrator` — node registry

Tracks the set of logical nodes and their active/inactive status. There is **no network transport here** — this is a local roster of which voices are currently participating.

```python
from infj_bot.hive_mind import HiveOrchestrator

orch = HiveOrchestrator()                  # 4 default nodes
orch.register_node("watcher-7")            # add a node
orch.deregister_node("seed-1")             # mark inactive (not removed)
status = orch.get_status()
# {
#   "node_count": 5,
#   "active_node_count": 4,
#   "nodes": [...],
#   "node_status": {...},
#   "status": "online",          # "offline" if no active nodes
# }
```

### Default nodes

| ID | Conventional role |
|----|-------------------|
| `spark-0`   | Primary cognition voice (DRIFT itself) |
| `seed-1`    | Memory/recall lane |
| `sprout-2`  | Synthesis / drafting |
| `lantern-4` | Safety / watcher (hardwired veto via TABLED) |

Custom rosters can be passed to the constructor: `HiveOrchestrator(nodes=["a", "b"])`.

---

## `ConsensusEngine` — propose → vote → resolve

In-process thread store keyed by 8-char thread ids. State is **not persisted** by this engine — the higher-level `commands.handle_hive_command` is responsible for writing outcomes to memory if desired.

```python
from infj_bot.hive_mind import (
    ConsensusEngine, DCPMessage, NodeRole, Resolution,
)

engine = ConsensusEngine()

# 1. Open a thread
msg = DCPMessage.thought("spark-0", NodeRole.PRIMARY, "Cache embeddings on disk")
thread = engine.propose(msg)

# 2. Collect votes
engine.vote(thread.thread_id, "lantern-4", "BLOCK")   # safety
engine.vote(thread.thread_id, "sprout-2", "ADOPT")    # synthesis
engine.vote(thread.thread_id, "seed-1",   "ADOPT")    # memory

# 3. Resolve
engine.resolve(
    thread.thread_id,
    Resolution.ADOPTED,
    final_position="Adopt: write-through chroma + 24h TTL",
)

# 4. Inspect open work
open_threads = engine.active_threads()
```

Each thread carries:

```python
ConsensusThread(
    thread_id="ab12cd34",
    original_thought=<DCPMessage>,
    state=ThreadState.OPEN | ThreadState.RESOLVED,
    resolution=<DCPMessage|None>,    # set by resolve()
    votes={voter_id: "ADOPT"|"BLOCK"|...},
)
```

`resolve()` builds a synthetic `DCPMessage` whose `payload` captures the full voting record and final position — that becomes the audit trail for whatever store the caller writes it to.

---

## Safety semantics

The watcher / safety node (`lantern-4` by default) is **not granted programmatic veto** at this layer — the engine is pure data. The convention enforced by `core/commands.py` is:

- Proposals that touch backdoors, guardrail bypasses, or scope-rail violations should be `TABLED` rather than `REJECTED`. `TABLED` means "preserved for audit, will not act".
- Resolutions other than `ADOPTED` must not result in tool execution.

If you wire `hive_mind` into anything that takes action, **gate execution on `resolution == ADOPTED`** explicitly.

---

## How it surfaces in the running bot

| Surface | Behavior |
|---------|----------|
| `/hive`                      | Shows `HiveOrchestrator.get_status()` plus open thread count |
| `/hive propose <thought>`    | Calls `ConsensusEngine.propose`, simulates role votes, resolves |
| `GET /api/hive`              | JSON dump of orchestrator status + open threads |
| `core/cognitive_orchestrator.py` | Subscribes to spotlight events; high-salience items can auto-propose |
| `core/hive/elysium.py`       | Heavier engine — uses `ConsensusEngine` for cross-voice resolution |

The Elysium subcommands (`/hive nexus decide`, `/hive reflect`, `/hive council status`) belong to the **separate** `core/hive/` package; `hive_mind/` does not implement persistent self-models or council energy.

---

## Tests

```bash
pytest tests/test_elysium.py -v          # exercises the engine end-to-end
```

`tests/test_elysium.py` is the canonical integration of both layers and is the recommended starting point for changes here. The hive_mind tests skip cleanly if the package is unavailable (see `76db68d` and `4f7a108`).

---

## Constraints & gotchas

- **Not threadsafe.** `ConsensusEngine` mutates a single `dict`. Wrap calls in a lock if you call it from background tasks.
- **No persistence.** Restarting the process forgets all threads. Mirror outcomes into `memory.py` if you need them after a reboot.
- **No network transport.** `source_node` is a label, not an address. There is no socket layer in this package today (despite the "distributed" in DCP).
- **Resolution must be authoritative.** Vote counts are stored but not tallied automatically — the caller decides which `Resolution` to record.

---

## Related docs

- [HIVE_ROADMAP.md](HIVE_ROADMAP.md) — phases and future capabilities
- [`core/hive/INDEX.md`](../core/hive/INDEX.md) — Elysium / Nexus / Council of 7
- [HOW_INFJ_BOT_WORKS.md](HOW_INFJ_BOT_WORKS.md) — overall request flow
- [GLOSSARY.md](GLOSSARY.md) — DCP, Resolution, NodeRole definitions
