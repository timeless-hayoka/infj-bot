# Hive Mind & Elysium — Distributed Cognition Guide

> Operator + developer reference for the two-tier distributed cognition stack:
> the lightweight `hive_mind/` consensus engine and the persistent `core/hive/`
> Elysium council. Source of truth for everything `/hive ...` and `/api/hive`.

This document covers what the subsystem is, the file layout, the on-disk
state, the public Python API, the user-facing commands, and the failure
modes you are likely to hit while running it.

---

## 1. Two tiers at a glance

The Hive is intentionally split into two layers with different lifetimes:

| Tier | Location | Purpose | State |
|------|----------|---------|-------|
| **Consensus tier** | `hive_mind/` | Stateless, in-process thread voting used by `/hive propose` and self-modification review. | In-memory only. |
| **Elysium tier**   | `core/hive/` | Persistent Council of 7 + Nexus self-model running the full Nexus Loop deliberation. | SQLite under `INFJ_DATA_DIR`. |

The two tiers are wired together through `core/coordination.py` (the
`Coordination` plugin), which surfaces consensus threads into the prompt and
escalates pending self-modification proposals to the consensus engine.

```
        ┌────────────────────────────── interfaces ──────────────────────────────┐
        │  CLI / Web  →  /hive ...   ·   FastAPI /api/hive   ·   coordination    │
        └───────────────────────────────────────────────────────────────────────┘
                       │                                       │
                       ▼                                       ▼
        ┌─────────────────────────────┐         ┌─────────────────────────────┐
        │  hive_mind/                 │         │  core/hive/                 │
        │  ConsensusEngine            │         │  ElysiumEngine              │
        │  HiveOrchestrator           │         │  NexusSelfModel             │
        │  DCPMessage / Resolution    │         │  Council  (7 members)       │
        │  in-memory threads          │         │  SQLite: nexus / council /  │
        │                             │         │           elysium .db       │
        └─────────────────────────────┘         └─────────────────────────────┘
```

---

## 2. File layout

### Consensus tier (`hive_mind/`)

| File | What it provides |
|------|------------------|
| `hive_mind/__init__.py` | Re-exports `ConsensusEngine`, `HiveOrchestrator`, `DCPMessage`, `NodeRole`, `Resolution`. |
| `hive_mind/consensus_engine.py` | `ConsensusEngine` (`propose`, `vote`, `resolve`, `active_threads`) and `ConsensusThread` dataclass. Threads live in an in-process dict; no persistence. |
| `hive_mind/orchestrator.py` | `HiveOrchestrator` — node registry / heartbeat. Default nodes: `spark-0`, `seed-1`, `sprout-2`, `lantern-4`. |
| `hive_mind/protocol/dcp.py` | Distributed Cognition Protocol — `DCPMessage`, `NodeRole` (`PRIMARY` / `CRITIC` / `BACKUP` / `OBSERVER`), `Resolution` (`ADOPTED` / `TABLED` / `REJECTED` / `PENDING`). |

### Elysium tier (`core/hive/`)

| File | What it provides |
|------|------------------|
| `core/hive/__init__.py` | Re-exports `NexusSelfModel`, `get_nexus`, `CouncilMember`, `CouncilRole`, `ElysiumEngine`, `get_elysium`. |
| `core/hive/elysium.py` | `ElysiumEngine` — async `decide(goal)`, `reflect(trigger)`, `council_status()`, plus the 5-stage Nexus Loop. |
| `core/hive/nexus.py` | `NexusSelfModel` — persistent self-model: goals, moral stances, narrative arc, active tensions, coherence score. |
| `core/hive/council_member.py` | `CouncilMember`, `CouncilRole`, `Council` container, `MemoryViewFilter`, `Proposal`, `Critique`. |
| `core/hive/INDEX.md` | File-level index (paths and quick test commands). |

### Wiring

| File | Role |
|------|------|
| `core/coordination.py` | `Coordination` plugin: keeps active consensus threads visible in prompts and pushes pending `self_modify` proposals to the Hive. |
| `core/commands.py` | `/hive ...` slash command handlers (see [§5](#5-commands)). |
| `interfaces/api.py` | `GET /api/hive` returns `HiveOrchestrator.get_status()`. |
| `tests/test_elysium.py` | 10 smoke tests covering Nexus, Council, and Elysium. |

---

## 3. On-disk state

All Hive SQLite files live under `DATA_DIR` (`INFJ_DATA_DIR` if set, otherwise
the project root). They are created on first use; **deleting them resets the
self-model and council history without breaking the codebase**.

| File | Owner | Tables |
|------|-------|--------|
| `nexus.db`   | `NexusSelfModel` | `nexus_state`, `nexus_decisions`, `nexus_reflections` |
| `council.db` | `CouncilMember` / `Council` | `council_members`, `council_proposals`, `council_critiques` |
| `elysium.db` | `ElysiumEngine` | `elysium_deliberations`, `elysium_reflections` |

`nexus_state` is a single-row table keyed on `id = 1` containing the full
serialized `NexusState` JSON. Decisions and reflections are append-only
history rows.

The consensus tier has **no SQLite footprint** — restart the process and all
in-flight threads disappear. Resolved self-modification outcomes are written
back to `self_modify.db` by `Coordination._apply_hive_resolution`.

---

## 4. The Nexus Loop

`ElysiumEngine.decide(goal)` runs five stages, each implemented as an
internal `_…` method on the engine:

1. **Ignition** (`_ignite`) — Recall up to 15 DMU-weighted memories from the
   unified `MemoryManager`. If no memory is wired, returns `[]` and the loop
   continues with empty context.
2. **Parallel Proposal** (`_generate_proposals`) — Each of the seven
   `CouncilMember`s scores the recalled memories through its
   `MemoryViewFilter` (fractal subspace), then generates a `Proposal`.
   If `brain` is wired, the member calls the LLM with its role signature;
   otherwise a deterministic template is used (`_role_angle`).
3. **Critique Tournament** (`_critique_tournament`) — Every member critiques
   every other member's proposal. Critiques are scored on the critic's
   role-specific axis (Logic penalises low confidence, Ethos penalises low
   moral weight, etc.).
4. **Nexus Integration** (`_nexus_integrate`) — Weighted aggregation of each
   proposal's `confidence`, `moral_weight`, `narrative_weight`, and average
   critique score:

   ```
   score = 0.30 * confidence
         + 0.25 * moral_weight
         + 0.20 * narrative_weight
         + 0.25 * mean(critique_scores)   # 0.125 if no critiques
   ```
5. **Resolution** (`_resolve`) — Normalise scores into vote probabilities,
   pick the top role. If no role exceeds 40%, the resolution is replaced
   with a composite (`[Composite] No single voice dominated. …`) and the
   winning role becomes `Nexus`.

After resolution, the engine:

- Records a winning vote on the winning `CouncilMember` and drains every
  member's energy by 0.05.
- Calls `NexusSelfModel.integrate_decision` to append a turning point,
  reinforce matching moral stances, and adjust coherence.
- Writes a `hive_decision` `Event` to the unified memory with `salience=0.95`
  and tags `["elysium", "nexus_decision", <role>]`.
- Persists a row to `elysium_deliberations`.

`ElysiumEngine.reflect(trigger)` is the cheaper background path: it samples
the council's lowest-energy member, names the dominant active tension,
records the insight in `elysium_reflections`, and lets the Nexus reduce that
tension's intensity if it appears in the insight text.

---

## 5. Commands

Implemented in `core/commands.py::handle_hive_command`.

| Command | Behaviour |
|---------|-----------|
| `/hive` | Status summary: active node count from `HiveOrchestrator`, plus the prompt-side hive summary from `Coordination.format_prompt`. |
| `/hive propose <thought>` | Opens a `ConsensusEngine` thread. The handler simulates votes from `seed-1`/`sprout-2`/`lantern-4`. Thoughts containing `"backdoor"` or `"ignore guardrails"` are auto-`TABLED` with a safety violation note — this is a hardwired guard. |
| `/hive nexus decide <goal>` | Runs the full async `ElysiumEngine.decide(goal)` via `asyncio.run` and prints the resolution, winning voice, moral / narrative weights, and per-role vote share. |
| `/hive reflect` | Calls `ElysiumEngine.reflect(trigger="user")` and prints the insight. |
| `/hive council status` | Prints each member's energy, deliberation count, win count, plus Nexus coherence and global decision/reflection counters. |

Anything else returns the usage hint:

```
Unknown hive subcommand.
Usage: /hive | /hive propose <thought> | /hive nexus decide <goal> | /hive reflect | /hive council status
```

If `/hive` is reached while `Coordination.consensus` is `None` (the
`ImportError` fallback in `core/coordination.py`), the handler short-circuits
with `"The Hive Mind is currently disconnected or offline."`.

---

## 6. API endpoint

`GET /api/hive` (defined in `interfaces/api.py`) returns the raw
`HiveOrchestrator.get_status()` payload:

```json
{
  "node_count": 4,
  "active_node_count": 4,
  "nodes": ["spark-0", "seed-1", "sprout-2", "lantern-4"],
  "node_status": {"spark-0": "active", "seed-1": "active", ...},
  "status": "online"
}
```

`GET /api/health` embeds the same payload under `"hive"` (or the string
`"offline"` if the orchestrator fails to import). There is currently **no
HTTP endpoint that triggers a Nexus Loop** — Elysium is only reachable via
the `/hive nexus decide` slash command.

---

## 7. The Council of 7

Defined in `core/hive/council_member.py`. Each member has a fixed
`CouncilRole`, a signature prompt, and a default `MemoryViewFilter`:

| Role | Mapping | Filter focus |
|------|---------|--------------|
| **Aura**   | emotional field | `emotional_bias=+0.3`, boosts: emotion, attachment, resonance |
| **Logic**  | cognition       | `dmu_threshold=0.3`, boosts: system, bug, architecture |
| **Meme**   | metacognition   | boosts: pattern, recursion, irony, history |
| **Vibe**   | intuition       | `emotional_bias=+0.2`, boosts: possibility, future, intuition |
| **Ethos**  | values          | boosts: value, moral, harm, growth |
| **Pulse**  | homeostasis     | boosts: energy, safety, need, stress |
| **Nexus**  | coordination    | `dmu_threshold=0.0` (sees everything) |

`MemoryViewFilter.score_memory` returns a 0–1 relevance score per memory
based on topic-keyword hits and emotional alignment. Memories below `0.3`
are filtered out before that member's proposal stage.

Members evolve across runs:

- `energy_level` rises during proposals/wins and is drained 0.05 per
  deliberation (and 0.10 on `drain()` after losing critiques).
- `win_count` boosts that member's proposal confidence on subsequent loops
  (`+0.05` per win, capped at `0.95`).
- All counters and the current `MemoryViewFilter` are serialised in
  `council_members.state_json`.

---

## 8. The Nexus self-model

`NexusSelfModel` (`core/hive/nexus.py`) carries DRIFT's identity across
loops. Important fields on `NexusState`:

- `current_goals` — capped to 20 entries, newest first.
- `moral_stances` — `Dict[principle → MoralStance]`. Reinforced when the
  goal or resolution mentions the principle.
- `narrative_arc` — `chapter`, `summary`, `turning_points` (last 50),
  `projected_next`.
- `active_tensions` — `ActiveTension` objects with `name`, `poles`,
  `intensity`. Reflection that names a tension reduces its `intensity` by 0.1
  and bumps `coherence_score` by 0.05.
- `coherence_score` — clamped to `[0, 1]`. Updated after each decision by
  `+0.1 − variance(council_votes)`; low-variance loops increase coherence.

The Nexus is a process-wide singleton via `get_nexus()`. To inspect it from
a Python REPL:

```python
from infj_bot.core.hive.nexus import get_nexus
nx = get_nexus()
print(nx.get_state())
print(nx.get_decision_history(limit=5))
```

---

## 9. The Distributed Cognition Protocol (DCP)

`hive_mind/protocol/dcp.py` defines the wire-equivalent dataclass used to
carry thoughts between nodes (even though the current implementation runs
all nodes in one process):

```python
from infj_bot.hive_mind.protocol.dcp import DCPMessage, NodeRole, Resolution

msg = DCPMessage.thought(
    source_node="spark-0",
    source_role=NodeRole.PRIMARY,
    content="Propose merging shadow integration with predictor.",
    priority=0.7,
)
```

`ConsensusEngine` usage:

```python
from infj_bot.hive_mind import ConsensusEngine, Resolution

engine = ConsensusEngine()
thread = engine.propose(msg)
engine.vote(thread.thread_id, voter_id="lantern-4", vote="BLOCK")
engine.resolve(thread.thread_id, Resolution.TABLED,
               final_position="Safety veto.")
```

`Resolution` values:

| Value | Meaning |
|-------|---------|
| `PENDING`  | Default; thread still open. |
| `ADOPTED`  | Proposal accepted (e.g. self-modify proposal approved). |
| `TABLED`   | Safety / scope veto. Used by the `backdoor` / `ignore guardrails` guard in `commands.py`. |
| `REJECTED` | Proposal explicitly turned down by votes. |

`ConsensusThread.state` flips from `OPEN` to `RESOLVED` once `resolve()` is
called.

---

## 10. Self-modification flow

`core/coordination.py` is the only path that turns Hive resolutions back
into local action:

1. Every cognitive cycle, `Coordination.run_cycle` reads
   `self_modify.db::self_modify_proposals` for rows with `status='pending'`.
2. Each new proposal is wrapped in a `DCPMessage` (`action='self_modify'`,
   payload carries `proposal_id`, `area`, `description`, `observed_need`)
   and pushed to `ConsensusEngine.propose`.
3. When a thread is resolved (`ADOPTED` or anything else), the same cycle
   writes the matching `approved` or `rejected` status back to
   `self_modify_proposals` along with `reviewed_at`.

If you bypass the hive (`HAS_HIVE=False`, e.g. broken import), proposals
remain `pending` indefinitely; the consciousness loop still runs normally.

---

## 11. Background reflection

The consciousness loop in `interfaces/main.py` calls
`ElysiumEngine.reflect("background")` every ~25 iterations. Each reflection:

- Persists a row to `elysium_reflections`.
- Persists a row to `nexus_reflections` and may bump `coherence_score` if
  the insight names an active tension.

Reflections are intentionally cheap — they do not call the LLM. If you need
heavier introspection, run `/hive nexus decide <goal>` instead.

---

## 12. Testing

```bash
# Elysium-only smoke suite (no torch needed)
pytest tests/test_elysium.py -v
```

`tests/test_elysium.py` covers:

- Nexus state roundtrip, decision integration, tension resolution.
- Council member proposal (without and with brain), critique scoring,
  memory filters, container `Council`.
- `ElysiumEngine.decide`, `.reflect`, `.council_status` against
  `tempfile.TemporaryDirectory()` DB paths.

To run against the live hive command surface inside the bot:

```bash
python interfaces/main.py
> /hive
> /hive propose roll out shadow integration milestone
> /hive nexus decide "Should DRIFT prioritise outreach this week?"
> /hive council status
> /hive reflect
```

---

## 13. Common pitfalls

- **"Hive Mind currently disconnected or offline."** — `HAS_HIVE` is `False`
  in `core/coordination.py`. This happens when the `hive_mind` package fails
  to import (usually a stale install — run `pip install -e .` again).
- **Empty Elysium proposals.** — `ElysiumEngine` runs with `memory=None` if
  the bot wasn't constructed through `interfaces/main.py`. Ignition returns
  `[]` and council confidences fall back to defaults. Wire `memory=` and
  `brain=` when constructing `get_elysium` manually.
- **Resolutions stuck on `PENDING`.** — `ConsensusEngine` only resolves when
  someone calls `resolve()`. `/hive propose` simulates votes for the demo
  path; programmatic propositions need their own resolver.
- **Nexus state drift after a crash.** — Only `nexus_state` (`id=1`) is
  authoritative; decisions and reflections are append-only history. If a
  decision was written but `nexus_state` failed to save, replay is
  impossible — accept the inconsistency or wipe `nexus.db`.
- **`asyncio.run()` inside `/hive nexus decide`.** — The command handler
  uses `asyncio.run`, so it cannot be called from within an existing event
  loop. Inside the FastAPI handlers, call `await elysium.decide(goal)`
  directly instead.

---

## 14. Where to extend

- New council role → add to `CouncilRole` enum, add a `ROLE_SIGNATURES`
  entry, add a default `MemoryViewFilter` in `CouncilMember._default_filter`,
  and the `Council` container picks it up automatically.
- Add a hive HTTP trigger → expose a new FastAPI route in
  `interfaces/api.py` that calls `await get_elysium(memory, brain).decide(...)`.
- Cross-process consensus → swap the in-memory `ConsensusEngine._threads`
  dict for a shared store (Redis, SQLite). The `DCPMessage` dataclass is
  already JSON-serialisable.

---

## 15. Related docs

- [HIVE_ROADMAP.md](HIVE_ROADMAP.md) — design history and forward backlog.
- [HOW_INFJ_BOT_WORKS.md](HOW_INFJ_BOT_WORKS.md) — full architecture context.
- [GLOSSARY.md](GLOSSARY.md) — project-local term definitions.
- [../core/hive/INDEX.md](../core/hive/INDEX.md) — file-level index for the
  Elysium directory.
