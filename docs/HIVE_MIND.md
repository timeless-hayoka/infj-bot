# Hive Mind Package

**Package:** [`infj_bot.hive_mind`](../hive_mind/)
**Wired into:** `core/coordination.py` (cognitive plugin), `core/commands.py` (`/hive …` slash commands), `interfaces/api.py` (`/api/hive`).
**Roadmap context:** see [HIVE_ROADMAP.md](HIVE_ROADMAP.md).

The `hive_mind` package is the in-process kernel for the bot's distributed-cognition layer. It is intentionally small: the heavyweight orchestration logic lives in `core/hive/` (Elysium, Nexus, Council), while `hive_mind/` owns the **protocol** (DCP), the **consensus state machine**, and the **node registry**.

This document describes that minimal kernel — what is shipped, how the pieces fit together, and how callers in the main bot use them.

---

## 1. Layout

```
hive_mind/
├── __init__.py              # Re-exports ConsensusEngine, HiveOrchestrator, DCPMessage, NodeRole, Resolution
├── consensus_engine.py      # Thread state machine: propose → vote → resolve
├── orchestrator.py          # Node registry + heartbeat
└── protocol/
    ├── __init__.py
    └── dcp.py               # DCPMessage, NodeRole, Resolution
```

There is no separate `shared_memory.py` or `tests/` subfolder in this package — older notes referencing those are out of date.

---

## 2. Distributed Cognition Protocol (DCP)

`hive_mind/protocol/dcp.py` defines the wire-equivalent data structures used by every hive interaction.

### 2.1 `NodeRole`

| Role | Meaning |
|------|---------|
| `PRIMARY` | The originating voice — typically `spark-0`, the main bot. |
| `CRITIC` | A node responsible for pushback / red-team review. |
| `BACKUP` | A redundant primary used during failover. |
| `OBSERVER` | A read-only listener (logging, dashboards). |

### 2.2 `Resolution`

Outcomes of a consensus thread:

| Resolution | Meaning |
|------------|---------|
| `ADOPTED` | The proposal is accepted; downstream effects should be applied. |
| `TABLED` | Held without acceptance; safety vetoes use this. |
| `REJECTED` | Explicitly declined. |
| `PENDING` | Still open. |

### 2.3 `DCPMessage`

A single message in the protocol. Required fields are `source_node`, `source_role`, and `content`; everything else has a sensible default.

```python
from infj_bot.hive_mind.protocol.dcp import DCPMessage, NodeRole

msg = DCPMessage.thought(
    source_node="spark-0",
    source_role=NodeRole.PRIMARY,
    content="propose: add rate limiting to /api/chat",
    priority=0.6,
)
msg.payload["action"] = "user_proposal"
msg.payload["description"] = "..."
```

The `payload` dict is the bot's convention for proposal metadata (e.g. `action`, `description`, `proposal_id`, `area`, `observed_need` — see `core/coordination.py::_propose_to_hive`). `message_id` and `timestamp` are auto-generated.

The classmethod `DCPMessage.thought(...)` is the shortcut for the most common case (`name="thought"`).

---

## 3. `ConsensusEngine` — thread state machine

`hive_mind/consensus_engine.py` implements an in-process consensus loop. It is stateless beyond an in-memory dict of `ConsensusThread` objects keyed by short UUID prefix.

### 3.1 Lifecycle

```python
from infj_bot.hive_mind.consensus_engine import ConsensusEngine
from infj_bot.hive_mind.protocol.dcp import DCPMessage, NodeRole, Resolution

engine = ConsensusEngine()

# 1. Propose
msg = DCPMessage.thought("spark-0", NodeRole.PRIMARY, "ship X")
thread = engine.propose(msg)        # → ConsensusThread (state=OPEN)

# 2. Vote
engine.vote(thread.thread_id, "seed-1", "FOR")
engine.vote(thread.thread_id, "sprout-2", "FOR")
engine.vote(thread.thread_id, "lantern-4", "AGAINST")

# 3. Resolve
engine.resolve(
    thread.thread_id,
    Resolution.ADOPTED,
    final_position="Aligned with growth roadmap.",
)

assert thread.state.name == "RESOLVED"
assert thread.resolution.payload["voting_record"] == {
    "seed-1": "FOR", "sprout-2": "FOR", "lantern-4": "AGAINST"
}
```

`ConsensusThread.state` is one of:

| State | Meaning |
|-------|---------|
| `OPEN` | Accepting votes; no resolution. |
| `RESOLVED` | A resolution has been recorded; `thread.resolution` is the synthesized resolution `DCPMessage`. |

`engine.active_threads()` returns threads still in `OPEN`. The engine does **not** currently auto-tally — `resolve()` is called explicitly by the caller after applying whatever voting policy is appropriate (majority, weighted, safety-veto, …). The bot's current policy lives in `core/commands.py::handle_hive_command` (demo voting) and `core/coordination.py::_apply_hive_resolution` (effect application).

### 3.2 The resolution message

When `resolve()` succeeds, it constructs and attaches a synthetic `DCPMessage`:

```python
DCPMessage(
    source_node="consensus",
    source_role=NodeRole.PRIMARY,
    content=final_position,
    name=resolution.value,
    payload={
        "resolution": resolution.value,
        "final_position": final_position,
        "voting_record": dict(thread.votes),
    },
)
```

Callers should read `thread.resolution.payload["resolution"]` for the outcome and `thread.resolution.payload["voting_record"]` for the votes. The `payload` may also carry caller-supplied keys (e.g. `proposal_id`) when the original thought's payload is forwarded by upstream code.

---

## 4. `HiveOrchestrator` — node registry

`hive_mind/orchestrator.py` keeps track of which hive nodes are reachable. The default cohort is:

```python
_DEFAULT_NODES = ["spark-0", "seed-1", "sprout-2", "lantern-4"]
```

These names are mnemonics, not hostnames; the orchestrator currently does **not** open sockets — node liveness is an in-process flag toggled by `register_node` / `deregister_node`. The status report returned by `get_status()` is consumed by:

- `core/commands.py` — the `/hive` slash command surfaces `active_node_count / node_count`.
- `interfaces/api.py` — the `/api/hive` JSON endpoint.
- `core/hive/INDEX.md` flows and the Elysium council reflection in `core/hive/elysium.py`.

```python
from infj_bot.hive_mind.orchestrator import HiveOrchestrator

orch = HiveOrchestrator()                   # default cohort
orch.register_node("watcher-9")             # add or re-activate
orch.deregister_node("sprout-2")            # mark inactive (kept in roster)
orch.get_status()
# {
#   'node_count': 5,
#   'active_node_count': 4,
#   'nodes': ['spark-0', 'seed-1', 'sprout-2', 'lantern-4', 'watcher-9'],
#   'node_status': {...},
#   'status': 'online',
# }
```

`get_status()["status"]` is `"online"` if any node is active, `"offline"` otherwise — callers use this to decide whether to even attempt a proposal.

---

## 5. Wiring into the main bot

`core/coordination.py` is the integration point. It guards the imports so that the rest of the bot keeps running even if `hive_mind` is unavailable (the package historically lived on a removable SSD):

```python
try:
    from infj_bot.hive_mind.consensus_engine import ConsensusEngine
    from infj_bot.hive_mind.protocol.dcp import DCPMessage, NodeRole
    HAS_HIVE = True
except ImportError:
    HAS_HIVE = False
```

When the import succeeds, `Coordination` instantiates a process-wide `ConsensusEngine` and registers itself as a cognitive plugin (`prompt_section="cognitive"`, `cycle_priority=60`). On each cycle it:

1. Scans `self_modify.db` for pending self-modification proposals (`status='pending'`).
2. For each one not already in the engine, creates a DCP thought and proposes it (`_propose_to_hive`).
3. Walks every thread in the engine; if any are `RESOLVED`, applies their resolution back to `self_modify.db` (`approved` for `ADOPTED`, otherwise `rejected`).

The prompt formatter (`Coordination.format_prompt`) injects a one-line summary of active threads into the prompt, so the LLM is aware that it has open proposals under deliberation.

### 5.1 Slash commands

| Command | Handler | Effect |
|---------|---------|--------|
| `/hive` | `core/commands.py::handle_hive_command` | Prints `HiveOrchestrator.get_status()` + active-thread summary. |
| `/hive propose <thought>` | same | Creates a DCP thought, runs a small demo vote loop, returns the resolution. |
| `/hive nexus decide <goal>` | same | Delegates to `core/hive/elysium.py` (Elysium decision engine). |
| `/hive reflect` | same | Runs an Elysium reflection. |
| `/hive council status` | same | Prints Elysium council energy + Nexus coherence. |

The `propose` handler uses a hard-coded safety policy: thoughts containing `"backdoor"` or `"ignore guardrails"` are auto-`TABLED` with a `lantern-4` `BLOCK` vote. This is the source of truth used by `tests/test_bot.py::test_hive_propose_safety_veto`.

### 5.2 HTTP endpoint

`GET /api/hive` (`interfaces/api.py`) returns the orchestrator status plus the coordination prompt block, so external dashboards can show hive health without screen-scraping the CLI.

---

## 6. Testing

Hive tests live in `tests/test_bot.py` (`TestCommands.test_hive_command`, `test_hive_propose_command`, `test_hive_propose_safety_veto`). They are guarded by:

```python
try:
    from infj_bot.hive_mind.consensus_engine import ConsensusEngine
    HIVE_AVAILABLE = True
except (ImportError, ModuleNotFoundError):
    HIVE_AVAILABLE = False
```

and decorated with `@unittest.skipUnless(HIVE_AVAILABLE, ...)`, so the suite still passes on machines where the package is missing.

There is no dedicated `hive_mind/tests/` folder — earlier docs that mentioned `cd hive_mind && pytest tests/` predate the current layout.

---

## 7. Extending the package

If you add modules under `hive_mind/`, prefer the existing conventions:

- **Wire-style data only.** Anything that crosses node boundaries should be a `DCPMessage` (or a strict subclass). Avoid leaking dataclasses with framework-coupled types.
- **In-process first.** Treat `ConsensusEngine` as a single-host implementation. If you add a transport, layer it underneath the engine (engine takes/returns `DCPMessage`, transport handles delivery).
- **Don't import from `infj_bot.core` here.** The package must remain importable without dragging in the cognitive stack, so that `HAS_HIVE` gating in `core/coordination.py` stays honest.
- **Re-export new public symbols** from `hive_mind/__init__.py` and from `hive_mind/protocol/__init__.py` as appropriate.

---

## 8. Related

- [HIVE_ROADMAP.md](HIVE_ROADMAP.md) — phased plan; this kernel covers Phase 1 (visibility) and Phase 2 (first consensus loop).
- `core/coordination.py` — bot-side glue, self-modify proposal routing.
- `core/hive/elysium.py`, `core/hive/nexus.py`, `core/hive/council_member.py` — Elysium / Nexus / Council, the persistent "frontal lobe" built on top of this kernel.
- [HOW_INFJ_BOT_WORKS.md](HOW_INFJ_BOT_WORKS.md) — overall request flow, where the coordination plugin slots into prompt assembly.
