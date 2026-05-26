# Global Workspace — Tiered Attention

`core/global_workspace.py` implements the bot's attention model: a
**competition each cycle** between every active and surviving thought.
The winner becomes what the bot is *consciously attending to*. Runners-up
fill the active workspace. Items below the active threshold are not deleted —
they sink into **preconscious bands** and only get archived to SQLite when
their salience drops below a hard floor.

This file is the implementation reference for that subsystem. The high-level
"why" lives in the [README architecture section](../README.md#architecture).

---

## 1. Why this replaced the old workspace

The previous implementation had three issues that produced misleading metrics:

1. **Salience could only grow.** A `broadcast_count` repetition boost meant
   anything mentioned often pinned itself to the spotlight forever.
2. **Time decay was fake.** Decay was applied per "cycle" with no relation to
   wall-clock time.
3. **The spotlight was a `dict`, not a `Broadcast`.** Downstream consumers
   (`dii_tracker`, the orchestrator, `being`) had to special-case it, and many
   silently fell back to `None`.

The current module fixes all three. The contract is summarized at the top of
the file:

> Each cycle, ALL items (new submissions + surviving active + preconscious)
> compete by current salience. The winner becomes the spotlight; runners-up
> fill the active workspace; everything below active threshold goes to a
> preconscious tier grouped by salience band rather than being discarded;
> items below the archive threshold are logged to SQLite and evicted.

---

## 2. Tiers

| Tier | Rank | What it means | Capacity |
|------|-----|----------------|---------|
| **Spotlight** | 1 | The single item the bot is consciously attending to | 1 |
| **Active** | 2 .. N | Consciously available, included in the prompt | `ACTIVE_CAPACITY` = 5 |
| **Preconscious** | below active, above archive | Retained, not yet forgotten, grouped by salience band | `PRECONSCIOUS_CAPACITY` = 20 across all bands |
| **Archived** | below `ARCHIVE_THRESHOLD` (0.05) | Logged to `workspace.db`, evicted from memory | unbounded (on disk) |

Preconscious bands are computed from the **current** salience of each item:

| Band | Salience range |
|------|----------------|
| `strong`    | 0.6 – 1.0 |
| `moderate`  | 0.4 – 0.6 |
| `faint`     | 0.2 – 0.4 |
| `trace`     | 0.0 – 0.2 |

---

## 3. Salience and decay

Each `Broadcast` carries a base `salience` (set at submission), an optional
`emotion_tag`, an `intensity`, and a `timestamp`. `Broadcast.current_salience()`
returns:

```python
minutes  = max(0, (now - created).total_seconds() / 60)
decayed  = salience * ((1 - decay_rate) ** minutes)     # default decay_rate = 0.08 / min
boost    = min(0.25, intensity * 0.25) if intensity > 0.5 else 0.0
return clamp(decayed + boost, 0.0, 1.0)
```

Properties:

- **Decay is exponential in real minutes**, not in cycles.
- **High-intensity items get a bounded boost** (≤ 0.25). They cannot exceed 1.0,
  so a single dramatic event cannot pin itself in the spotlight forever.
- **There is no repetition boost.** Identical submissions are deduplicated
  by `(source, content[:80])` and the higher base salience wins.

---

## 4. One cycle, step by step

`GlobalWorkspace.cycle(context=None)`:

1. **Gather competitors.** Surviving active items + every preconscious band +
   the pending submission pool.
2. **Deduplicate** by `(source, content[:80])`, keeping the highest base
   salience.
3. **Sort** all survivors by `current_salience(now)` descending.
4. **Partition** into tiers:
   - If `current_salience < ARCHIVE_THRESHOLD` → queued for archive.
   - Else if active is not full → goes into active.
   - Else → placed into the matching preconscious band (until
     `PRECONSCIOUS_CAPACITY` is reached, then overflow is archived).
5. **Set the spotlight** to the top-ranked active item.
6. **Persist** archived entries into `workspace_history` and bump the cycle
   counter in `workspace_state`.

The pending pool is reset every cycle so submissions cannot stack across
cycles without competing again.

---

## 5. Persistence

| Storage | What it holds |
|---------|---------------|
| In-memory `WorkspaceState` | `contents` (active), `spotlight`, `cycle_count`, `broadcast_history` (last 50 winners) |
| In-memory `preconscious` dict | Lists keyed by band: `strong` / `moderate` / `faint` / `trace` |
| `workspace.db` → `workspace_history` | Archived broadcasts (`timestamp, source, content, salience, tier`) |
| `workspace.db` → `workspace_state` | `cycle_count` between restarts |

The database path is `DATA_DIR / "workspace.db"`, where `DATA_DIR` is resolved
by `core.config` (honors `INFJ_DATA_DIR`).

**The active workspace itself is not persisted across restarts.** Only the
cycle counter and the archive log survive. This is intentional: the active
workspace is *attention*, not memory — long-term storage belongs in
`core/memory.py` and `core/unified_memory.py`.

---

## 6. Public API

```python
from infj_bot.core.global_workspace import get_workspace

ws = get_workspace()                       # singleton

ws.submit(
    source="emotional_field",
    content="Tension rising on the conversation thread.",
    salience=0.7,
    emotion_tag="anxious",
    intensity=0.6,
)

ws.cycle()                                 # run the competition

ws.spotlight                               # Optional[Broadcast]
ws.contents                                # List[Broadcast] — full active set
ws.get_preconscious_summary()              # {band: [{source, content, salience}, ...]}
ws.format_prompt_snippet()                 # text injected into prompts
ws.get_stats()                             # {capacity, current_contents, cycle_count, ...}
ws.get_history(limit=10)                   # archived broadcasts from SQLite
ws.move_spotlight("rising tension")        # manual focus override (matches substring)
ws.reflect_on_workspace()                  # higher-order Broadcast or None
```

**Direct `.spotlight` and `.contents` access is part of the contract.**
Downstream consumers (`core/dii_tracker.py`, `core/being.py`,
`core/cognitive_orchestrator.py`, `interfaces/api.py`) read these properties
directly. Do not break the property names without updating those call sites.

---

## 7. Prompt injection

`format_prompt_snippet()` is what actually lands in the model context. Shape:

```
[Focus] <source>: <up-to-200-chars of spotlight content>
Active awareness:
  · [<source>] <up-to-120-chars>  (0.62)
  · [<source>] <up-to-120-chars>  (0.51)
Background (strong):
  · [<source>] <up-to-100-chars>
  · ...
```

Only one preconscious band is shown — the strongest populated one — to keep
the snippet bounded. If nothing is active or preconscious, the snippet is
`"Attention workspace: clear."`.

The plugin registration at the bottom of `global_workspace.py` runs
`format_prompt_snippet` in the `core` prompt section with `prompt_priority=3`,
so it appears near the top of assembled prompts.

---

## 8. Operator commands

`/workspace …` is handled by `handle_workspace_command` in `core/commands.py`:

| Command | Behavior |
|---------|---------|
| `/workspace status` (default) | `get_conscious_summary()` → same as `format_prompt_snippet()` |
| `/workspace history` | Last 10 archived broadcasts from `workspace.db` |
| `/workspace stats` | Capacity, cycle count, total broadcasts, spotlight source, sources in active workspace |
| `/workspace focus <content>` | Substring-matches against active items and forces the spotlight |
| `/workspace reflect` | Generates a `[metacognition]` broadcast describing the current themes |

`/workspace focus` only matches items already in the **active** workspace.
Preconscious items must first re-enter active via another `cycle()` (i.e., by
gaining salience).

---

## 9. Concurrency and registration

- All mutations go through `self._lock` (a single `threading.Lock`). The
  workspace is safe to call from background cycle threads and request handlers
  concurrently.
- `get_workspace()` is a module-level singleton. The first call constructs the
  `GlobalWorkspace`, opens the SQLite file, and reads back the cycle counter.
- On import, the module self-registers as a `CognitivePlugin`
  (`cycle_handler="cycle"`, `cycle_frequency=1`, `prompt_section="core"`,
  `is_core=True`), so it ticks on every consciousness loop iteration.

---

## 10. Gotchas

- **`get_history` reads `workspace_archive`, not `workspace_history`.** The
  initial schema in `_init_db` creates `workspace_history`; `get_history`
  currently queries a table named `workspace_archive`. On a fresh database the
  method silently returns `[]`. The CLI/API behavior is graceful, but treat
  `get_history` as best-effort until both names are reconciled.
- **Dedup key is the first 80 chars of content.** Two near-identical thoughts
  from the same source with a long shared prefix will collapse into one.
- **Preconscious overflow archives**. Items shoved out by `PRECONSCIOUS_CAPACITY`
  are written to `workspace_history` with the tier label `archived_overflow`.

---

## 11. Source

- `core/global_workspace.py` — implementation
- `core/commands.py` — `/workspace …` handlers
- `interfaces/api.py` — exposes spotlight, contents, and stats through
  `/api/observer`
- `core/dii_tracker.py`, `core/being.py` — direct consumers of
  `workspace.spotlight`
