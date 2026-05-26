# Tiered Attention Workspace

**Module:** [`core/global_workspace.py`](../core/global_workspace.py)
**Persistence:** `workspace.db` (under `INFJ_DATA_DIR`)
**Registered as:** core cognitive plugin `global_workspace` (cycle priority 3, prompt section `core`)

This document describes the attention model that replaced the earlier Global Workspace Theory (GWT) stub. The previous implementation had several failure modes that made it effectively a no-op (see [§ History](#5-history)). The current model is a real competition-based attention buffer with multiple tiers.

---

## 1. Intent

The workspace acts as the bot's short-term attention spine. Cognitive plugins (`being`, `shadow`, `homeostasis`, `predictor`, `temporal`, `relationship`, `creativity`, `aspirations`, `metacognition`, …) submit salient snippets and the workspace decides each cycle:

- **What is in focus right now** (the spotlight).
- **What is consciously available** for prompt assembly (the active set).
- **What lingers below threshold** without being lost (preconscious bands).
- **What has decayed below relevance** and should be archived for later inspection (SQLite log).

Downstream consumers read the workspace's state directly (e.g. `dii_tracker.py` uses `workspace.spotlight.salience` as the **ignition** component of the DII metric; `cognitive_orchestrator.py` calls `format_prompt_snippet()` when building chat prompts).

---

## 2. Tiers

Each cycle, every surviving item is re-ranked by **current salience** (base salience exponentially decayed by real elapsed time, with an emotional intensity boost). Items are then partitioned into four tiers:

| Tier | Rank | Capacity | Behaviour |
|------|------|----------|-----------|
| **Spotlight** | 1 | 1 | Single item currently being attended to. Drives prompt focus and DII ignition. |
| **Active** | 2..N | `ACTIVE_CAPACITY = 5` | Consciously available; included in prompt as "active awareness". |
| **Preconscious** | below active | `PRECONSCIOUS_CAPACITY = 20` across bands | Retained out-of-focus, grouped by salience band: `strong`, `moderate`, `faint`, `trace`. The strongest populated band appears in the prompt as background context. |
| **Archived** | salience < `ARCHIVE_THRESHOLD` (0.05) | unbounded | Written to `workspace.db.workspace_history` and evicted from memory. |

Salience bands used for the preconscious tier:

| Band | Salience range |
|------|----------------|
| `strong` | 0.6 – 1.0 |
| `moderate` | 0.4 – 0.6 |
| `faint` | 0.2 – 0.4 |
| `trace` | 0.0 – 0.2 |

If the preconscious tier is full, lower-ranked items overflow into the archive table with tier label `archived_overflow`.

---

## 3. Lifecycle of a submission

```python
from infj_bot.core.global_workspace import get_workspace

ws = get_workspace()
ws.submit(
    source="predictor",
    content="anomaly: heart-rate deviation 1.2σ above baseline",
    salience=0.7,
    emotion_tag="alert",
    intensity=0.6,
)
```

1. **Submit** — the item enters `self._pool`. It does **not** compete until the next `cycle()` call.
2. **Cycle** — typically triggered by `CognitiveOrchestrator` on the consciousness loop. The cycle:
   - Merges the pool with surviving active items and all preconscious bands.
   - Deduplicates on `(source, content[:80])`, keeping the highest **base** salience.
   - Sorts by **current salience** (decay applied from each item's original timestamp).
   - Walks the ranked list and assigns tiers until each capacity is full; overflow goes to the archive table.
   - Updates `state.spotlight`, `state.contents`, `preconscious`, and appends to `broadcast_history` (capped at 50 entries).
3. **Decay** — `Broadcast.current_salience()` applies `salience * (1 - decay_rate) ** minutes_elapsed`. Default `decay_rate = 0.08` (≈ 8 % loss per minute). High `intensity` (> 0.5) adds up to `+0.25` of boost.
4. **Archive** — once decayed below `ARCHIVE_THRESHOLD`, items are inserted into `workspace_history` with their final salience and the tier label that led to eviction.

### Notable properties

- **Time-based decay** — the previous implementation approximated decay as "one cycle = one minute"; now elapsed wall-clock time is used. Idle cycles no longer artificially evict everything.
- **No broadcast-count multiplier** — repeat broadcasts no longer compound salience; reissuing an item just updates the dedup entry with the higher base salience.
- **High-salience submissions can preempt stale active items** — because everything is re-ranked together each cycle.
- **Preconscious is sticky** — moderate-salience items linger in `faint`/`trace` bands instead of being thrown away, so the bot can resurface old themes when nothing more relevant is competing.

---

## 4. Public surface

| Member | Purpose |
|--------|---------|
| `submit(source, content, salience=0.5, emotion_tag=None, intensity=0.0)` | Queue a new broadcast for the next cycle. |
| `cycle(context=None)` | Run one competition cycle (called by the cognitive orchestrator). |
| `set_spotlight(content, source="", strength=1.0)` | Force the spotlight (used by callers that override attention manually). |
| `move_spotlight(content)` | Promote an existing active item to the spotlight; returns `True` on success. |
| `reflect_on_workspace()` | Return a synthesized `Broadcast` summarising 2+ active items (used by `metacognition`). |
| `format_prompt_snippet()` | Prompt-ready summary: spotlight + active + strongest preconscious band. |
| `get_conscious_summary()` | Alias of `format_prompt_snippet()` (used by older callers). |
| `get_preconscious_summary()` | Per-band dict of items, for inspection or `/workspace` style commands. |
| `get_stats()` | Snapshot of `capacity`, `current_contents`, `cycle_count`, `total_broadcasts`, `spotlight` source. |
| `get_history(limit=10)` | Recent archived broadcasts from `workspace.db`. |
| `spotlight` / `contents` (properties) | Direct access to the `Broadcast` and active list (used by `dii_tracker.py`, `api.py`). |
| `_submissions` (property) | Pending pool length, surfaced by the JSON API for diagnostics. |

`Broadcast` itself is the data class submitted into the workspace:

```python
@dataclass
class Broadcast:
    source: str
    content: str
    salience: float = 0.5
    emotion_tag: Optional[str] = None
    intensity: float = 0.0
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    decay_rate: float = 0.08  # fractional salience lost per minute
```

Callers should treat `salience` as a base value at submission time; if they need the time-decayed view they should call `broadcast.current_salience()`.

---

## 5. History

The previous workspace had four problems that effectively neutralised it:

1. **Spotlight was a dict** — code that assumed `.salience` (e.g. `dii_tracker`) threw and silently returned defaults.
2. **No preemption** — new high-salience items could not displace stale low-salience ones already in the active set.
3. **Per-cycle decay** — decay assumed "1 cycle == 1 minute", so during quiet stretches everything went to zero in a few ticks.
4. **Repeat-broadcast inflation** — repeated submissions multiplied salience, eventually pinning a single source as the spotlight indefinitely.

The current module fixes all four (see the docstring on `core/global_workspace.py`). The schema for `workspace.db` is forward-compatible: `workspace_history` is still keyed by `(timestamp, source, content, salience, tier)`, plus a new `workspace_state` table for the cycle counter.

---

## 6. Operational notes

- **Inspecting state at runtime:** `GET /api/system_state` (in `interfaces/api.py`) and the `/state` web endpoint include the workspace summary. The `/workspace` slash command (`core/commands.py`) prints active and preconscious tiers.
- **Configuring capacity:** tweak `ACTIVE_CAPACITY`, `PRECONSCIOUS_CAPACITY`, and `ARCHIVE_THRESHOLD` at the top of `core/global_workspace.py`. They are module-level constants — restart the process to apply changes.
- **Persistence path:** by default `WORKSPACE_DB = DATA_DIR / "workspace.db"`. Override `INFJ_DATA_DIR` to relocate (see [GLOSSARY.md](GLOSSARY.md#infj_data_dir)).
- **Thread safety:** `submit`, `cycle`, `move_spotlight`, and `reflect_on_workspace` all hold `self._lock`. External readers should not assume per-call atomicity across multiple methods.

---

## 7. Common pitfalls

- **Forgetting to call `cycle()`.** Submissions accumulate in `self._pool` until a cycle runs. In tests that exercise the workspace directly, call `ws.cycle()` explicitly — it does **not** happen on submit.
- **Treating `spotlight` as a dict.** It is a `Broadcast` instance. Use `ws.spotlight.salience`, not `ws.spotlight["salience"]`.
- **Assuming preconscious items survive forever.** They do not — once `current_salience()` drops below `ARCHIVE_THRESHOLD`, the next cycle archives them. If you need a survivor, refresh its `salience` by resubmitting with the same `(source, content)` key.
- **Mutating `workspace.contents` directly.** It is exposed as a property for read access. Use `move_spotlight()` or `submit() + cycle()` to mutate state safely.
- **Using `salience` directly when ranking.** Use `current_salience(now)` — the raw `salience` attribute does not reflect decay.

---

## 8. Related

- [HOW_INFJ_BOT_WORKS.md](HOW_INFJ_BOT_WORKS.md) — end-to-end chat-turn flow; the workspace plugs into prompt assembly via `cognitive_orchestrator.assemble_prompt`.
- [GLOSSARY.md](GLOSSARY.md) — short definitions for `Broadcast`, `Spotlight`, `Preconscious`, `Cognitive plugin`.
- `core/dii_tracker.py` — uses `workspace.spotlight.salience` as the ignition component of DII.
- `core/metacognition.py` — periodically inspects active contents and may submit a higher-order reflection back into the workspace.
