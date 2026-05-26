# Hive Mind — Distributed Cognition

The Hive Mind is PHI // DRIFT's lightweight in-process layer for **multi-voice
deliberation**. It lets parts of the system propose thoughts, vote, and resolve
threads with an auditable record — without any network dependency or external
service.

This document covers two related packages that work together:

| Package | Role | Status |
|---------|------|--------|
| `hive_mind/` | Protocol, consensus engine, and node registry | New in this PR |
| `core/hive/` | **Elysium** — persistent self-model + 7 council voices | Phase 5 (already shipped) |

The `hive_mind/` package is the **transport and bookkeeping layer**.
The `core/hive/` package is the **higher-level deliberation engine** that consumes it.

---

## 1. Why two layers

The bot has two distinct distributed-cognition needs:

1. **Lightweight consensus** for individual proposals — e.g. a self-modification
   suggestion or a `/hive propose` from the operator. These need a thread,
   votes, a resolution, and a record. Cheap, synchronous, no LLM call required.

2. **Deeper deliberation** for whole goals — multiple voices reading shared
   memory through different filters, generating proposals and critiques,
   converging on a winning position. Slower, async, uses the brain.

`hive_mind/` solves (1). `core/hive/` (Elysium) solves (2) and uses
`hive_mind/` internally for its protocol primitives.

---

## 2. `hive_mind/` — protocol and consensus

### 2.1 Modules

```
hive_mind/
├── __init__.py            # public exports
├── consensus_engine.py    # ConsensusEngine: threads, votes, resolutions
├── orchestrator.py        # HiveOrchestrator: node registry + heartbeat
└── protocol/
    └── dcp.py             # Distributed Cognition Protocol: DCPMessage, roles, resolutions
```

Top-level imports:

```python
from infj_bot.hive_mind import (
    ConsensusEngine,
    HiveOrchestrator,
    DCPMessage,
    NodeRole,
    Resolution,
)
```

### 2.2 The Distributed Cognition Protocol (DCP)

Every thought traveling through the Hive is a `DCPMessage` —
a small dataclass in `hive_mind/protocol/dcp.py`:

| Field | Type | Notes |
|------|------|-------|
| `source_node` | `str` | Logical sender (e.g. `"spark-0"`, `"lantern-4"`) |
| `source_role` | `NodeRole` | `PRIMARY`, `CRITIC`, `BACKUP`, or `OBSERVER` |
| `content` | `str` | Free-form thought text |
| `name` | `str` | Default `"thought"`; resolutions use the `Resolution` value |
| `priority` | `float` | Default `0.5`; used as a soft scheduling hint |
| `payload` | `dict` | Structured side-data (e.g. `proposal_id`, `action`, `voting_record`) |
| `message_id` | `str` | Auto-generated 8-char id |
| `timestamp` | `str` | ISO-8601, set on construction |

Convenience constructor:

```python
msg = DCPMessage.thought(
    source_node="spark-0",
    source_role=NodeRole.PRIMARY,
    content="Adopt the new homeostasis decay curve.",
    priority=0.7,
)
```

`Resolution` is the closed set of thread outcomes:
`ADOPTED`, `TABLED`, `REJECTED`, `PENDING`.

### 2.3 `ConsensusEngine`

`ConsensusEngine` keeps an in-memory dictionary of `ConsensusThread`s.
Each thread carries the original proposal, a `state` (`OPEN` / `RESOLVED`),
a `votes` map keyed by voter id, and (after resolution) a final `DCPMessage`
containing the resolution payload and the full voting record.

Lifecycle:

```python
engine = ConsensusEngine()

thread  = engine.propose(msg)                            # OPEN
engine.vote(thread.thread_id, "seed-1",    "FOR")
engine.vote(thread.thread_id, "sprout-2",  "FOR")
engine.vote(thread.thread_id, "lantern-4", "BLOCK")      # safety node
engine.resolve(
    thread.thread_id,
    Resolution.TABLED,
    final_position="Blocked by safety lane.",
)
```

After `resolve`, `thread.resolution` is a `DCPMessage` whose
`payload["voting_record"]` preserves the per-voter ballot.
`engine.active_threads()` returns only `OPEN` threads.

**Threads are in-process only.** They live as long as the engine instance does.
Anything that must survive a restart (e.g. self-modification proposals) is
persisted separately by `core/coordination.py` into SQLite.

### 2.4 `HiveOrchestrator`

`HiveOrchestrator` is a tiny node registry. It does **not** dispatch work — it
just tracks which logical nodes exist and whether they're `"active"` or
`"inactive"`. Defaults are `spark-0`, `seed-1`, `sprout-2`, `lantern-4`.

```python
orch = HiveOrchestrator()
orch.register_node("watcher-7")
orch.deregister_node("seed-1")
orch.get_status()
# → {"node_count": 5, "active_node_count": 4, "nodes": [...], "node_status": {...}, "status": "online"}
```

`/hive` (no args) and the `/api/hive` endpoint surface this status to operators.

---

## 3. `core/coordination.py` — the bot's bridge into the Hive

`core/coordination.py` is the only place that **wires the Hive into the
cognitive loop**. It is registered as a cognitive plugin
(`prompt_section="cognitive"`, `cycle_priority=60`) so it runs on every cycle.

Responsibilities:

| Method | What it does |
|--------|--------------|
| `__init__` | Instantiates `ConsensusEngine` (or sets `self.consensus = None` if `hive_mind` is missing) |
| `run_cycle` | Per-cycle tick: push new self-modification proposals into the Hive, then apply any RESOLVED threads back to local SQLite |
| `_sync_self_modification_proposals` | Reads `data/self_modify.db` for `status='pending'` rows; submits any not already in consensus |
| `_apply_hive_resolution` | When a thread for a `proposal_id` resolves, updates `self_modify_proposals.status` to `approved` or `rejected` |
| `format_prompt` | Injects "the Hive is debating N proposals…" into the prompt |

If `hive_mind` is not importable, `Coordination.consensus` is `None` and all
methods fall through cleanly — the rest of the bot continues to work.

---

## 4. Operator commands (`/hive …`)

All commands live in `core/commands.py` (`handle_hive_command`). They share a
single `Coordination` singleton via `get_coordination()`.

| Command | Implementation | Effect |
|---------|----------------|--------|
| `/hive` | `HiveOrchestrator().get_status()` + `Coordination.format_prompt()` | Active node count + summary of open threads |
| `/hive propose <thought>` | `coord.consensus.propose(...)`, then simulated votes | Opens a thread; if text contains `backdoor` or `ignore guardrails`, `lantern-4` casts `BLOCK` and the thread is `TABLED` |
| `/hive nexus decide <goal>` | `core/hive/elysium.ElysiumEngine.decide()` | Async full council deliberation; returns winning role + per-voice votes |
| `/hive reflect` | `core/hive/elysium.ElysiumEngine.reflect()` | Runs a Nexus reflection cycle |
| `/hive council status` | `core/hive/elysium.ElysiumEngine.council_status()` | Per-voice energy and win counts |

**Safety lane behavior.** The `/hive propose` handler hardwires a refusal path
for proposals that mention backdoors or guardrail bypasses. That decision is
made in `handle_hive_command`, not inside the engine — `ConsensusEngine` itself
treats votes as opaque strings.

---

## 5. `core/hive/` — Elysium

`core/hive/` builds on top of `hive_mind/` to add a persistent self-model
(**Nexus**) and seven council voices (Aura, Logic, Meme, Vibe, Ethos, Pulse,
Nexus). It is documented in detail in
[`core/hive/INDEX.md`](../core/hive/INDEX.md) and tracked in
[`HIVE_ROADMAP.md`](HIVE_ROADMAP.md) Phase 5.

Relationship summary:

```
operator / API
     │
     ▼
core/commands.py  ──┐
                    ├──► core/coordination.py ──► hive_mind/ (ConsensusEngine, HiveOrchestrator)
                    └──► core/hive/elysium.py ──► nexus.db, council.db, elysium.db
```

Elysium uses `hive_mind` types (`DCPMessage`, `NodeRole`, `Resolution`) where
it needs protocol primitives, but its deliberation logic and durable state are
its own.

---

## 6. Failure modes and operational notes

- **Missing package.** If `hive_mind` cannot be imported, `Coordination.consensus`
  is `None`, `/hive` returns *"The Hive Mind is currently disconnected or
  offline."*, and `format_prompt()` returns *"The Hive Mind is currently
  disconnected."* Tests in `tests/test_bot.py` skip gracefully via the same
  import guard.
- **Restarts wipe live threads.** `ConsensusEngine` holds threads in memory only.
  Anything that must survive a restart (currently only self-modification
  proposals) is re-published from SQLite on the next `run_cycle`.
- **No network code.** `hive_mind/` is intentionally local. There is no
  serialization layer, no transport, and no auth in this package. If you ever
  add a remote node, build that layer outside and call into `ConsensusEngine`.
- **Vote strings are free-form.** Today the codebase uses `"FOR"`, `"BLOCK"`,
  and similar uppercase tokens. The engine does not enforce a vocabulary — keep
  conventions consistent at the call site.

---

## 7. Further reading

- [`core/hive/INDEX.md`](../core/hive/INDEX.md) — Elysium internal index
- [`HIVE_ROADMAP.md`](HIVE_ROADMAP.md) — phased plan; Phases 1, 2, and 5 are shipped
- [`HOW_INFJ_BOT_WORKS.md`](HOW_INFJ_BOT_WORKS.md) — full one-turn walkthrough
- Source:
  - `hive_mind/consensus_engine.py`
  - `hive_mind/orchestrator.py`
  - `hive_mind/protocol/dcp.py`
  - `core/coordination.py`
  - `core/commands.py` — `handle_hive_command`
