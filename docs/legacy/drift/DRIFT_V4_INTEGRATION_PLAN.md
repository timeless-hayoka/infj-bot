# DRIFT V4 Integration Plan

## Pre-Flight Assessment

**Codebase:** `/media/crexs/PortableSSD/drift/drift_repo_tmp/`  
**Target:** Integrate PSC (Predictive Salience Cascading) V4 architecture  
**Constraint:** 219+ tests must pass; no cyber boundary changes  

---

## Critical Finding: `global_workspace.py` is Corrupted

The current `drift/core/global_workspace.py` is **incomplete**. It defines the class twice, has no `submit()`, `compete()`, `cycle()`, `move_spotlight()`, or `format_prompt_snippet()` methods, yet:

- `cognitive_orchestrator.py` calls `self.workspace.cycle(context)`
- `tests/core/test_global_workspace.py` tests all these missing methods
- `being.py` calls `ws.submit(...)` via `evolve_cycle()`

**This means the test suite is currently broken before we even start V4 integration.**

### Step 0 (BLOCKING): Restore Global Workspace
Before any V4 work, we must reconstruct `global_workspace.py` to satisfy existing tests.

**Source of truth:** `tests/core/test_global_workspace.py` — it specifies the exact API surface:
- `Broadcast(source, content, salience, emotion_tag, intensity, decay_rate, broadcast_count)`
  - `.current_salience(minutes_elapsed)`
  - `.broadcast_count`
- `GlobalWorkspace(db_path, capacity)`
  - `.submit(source, content, salience, emotion_tag, intensity)`
  - `.compete()` → returns `List[Broadcast]`
  - `.move_spotlight(content)` → bool
  - `.auto_spotlight()`
  - `.reflect_on_workspace()` → Optional[Broadcast]
  - `.format_prompt_snippet()` → str
  - `.cycle(ctx)` → runs competition + periodic reflection
  - `.get_broadcast()` → List[Broadcast]
  - `.state` → WorkspaceState(capacity, contents, spotlight, spotlight_source, cycle_count, total_broadcasts)

**Decision:** Rebuild `global_workspace.py` from test expectations + existing DB schema. This is ~150 lines of restoration.

---

## V4 Integration Steps (in order)

### Step 1: Add Core V4 Files
Copy into `drift/core/`:
```
psc_scaled.py      → drift/core/psc_scaled.py
being_snapshot.py  → drift/core/being_snapshot.py
dmu.py             → drift/core/dmu.py
```

**Minor fix needed:** `being_snapshot.py` imports `datetime` via `__import__` inline — clean that up to a proper top-level import.

**Field mapping audit:** `being_snapshot.py` `FIELD_MAP` expects fields like `mood`, `energy`, `curiosity`, `attachment`, `focus`, `insights_formed`, `shadow_depth`, `volition`, `autonomy_drive`, `purpose_alignment`, `coherence`, `integration`, `connection`, `growth`, `autonomy`, `integrity`.

Current `CognitiveState` has: `mood, energy, intensity, curiosity, attachment, focus, last_thought, last_interaction, total_interactions, insights_formed, dreams_had`.
Current `AgencyState` has: `volition, self_awareness, architecture_awareness, autonomy_drive, purpose_alignment, last_choice, last_choice_time`.

**Gap:** `being_snapshot.py` maps `shadow_depth` → `threat_pressure`, but `Being` has no `shadow_depth` field. It also maps `coherence`, `integration`, `connection`, `growth`, `autonomy`, `integrity` which come from `HomeostaticRegulator`, not `CognitiveState`.

**Decision:** In the snapshot writer, merge `CognitiveState`, `AgencyState`, and `HomeostaticRegulator` state into one dict before writing. Gracefully skip missing fields.

---

### Step 2: Patch `being.py` for Telemetry

**Insertion point:** End of `evolve()` method (line 265, after `self._save_state()`).

```python
# Add at top of being.py:
try:
    from drift.core.being_snapshot import snapshot_cognitive_state
    _SNAPSHOT_ENABLED = True
except ImportError:
    _SNAPSHOT_ENABLED = False

# Add at end of evolve():
if _SNAPSHOT_ENABLED:
    # Merge all available state for PSC dimensions
    merged = {
        **self.state.to_dict(),
        **{k: getattr(self.agency, k) for k in self.agency.__dataclass_fields__},
    }
    # Pull homeostasis fields if available
    try:
        from drift.core.homeostasis import HomeostaticRegulator
        reg = HomeostaticRegulator()
        for need_name, need in reg.needs.items():
            merged[need_name] = need.current
    except Exception:
        pass
    snapshot_cognitive_state(
        merged,
        session_id=getattr(self, 'session_id', ''),
        cycle=getattr(self, 'state', None) and getattr(self.state, 'total_interactions', 0),
    )
```

---

### Step 3: Patch `global_workspace.py` for PSC Anticipatory Layer

**Requires Step 0 completion first.**

Add to `GlobalWorkspace.__init__`:
```python
try:
    from drift.core.psc_scaled import PSCBatchEngine, DIMENSION_POLARITY
    self._psc_engine = PSCBatchEngine(list(DIMENSION_POLARITY.keys()), policy="BALANCED")
    self._psc_cycle_count = 0
except ImportError:
    self._psc_engine = None
```

Add method `_run_psc_cycle(self, current_state: dict)` — see `global_workspace_psc_patch.py` for full implementation.

**Call site:** Inside `cycle()` method, before `compete()`:
```python
def cycle(self, context):
    self.state.cycle_count += 1
    # Build current state dict from being + homeostasis
    state_dict = self._gather_cognitive_state()
    self._run_psc_cycle(state_dict)
    self.compete()
    # ... rest of cycle
```

**Note:** `_gather_cognitive_state()` needs to collect normalized values from `get_being()` and `HomeostaticRegulator`. This is a new helper.

---

### Step 4: Patch `cognition.py` for Predictive Dissonance (Optional)

Current `cognition.py` is functional-style: `detect_dissonance(text) -> dict`. The V4 patch expects a class with `_psc_dissonance_component()`.

**Decision:** Wrap the existing function rather than refactor. Add a new function:
```python
def detect_dissonance_with_psc(text: str, psc_engine=None) -> dict:
    result = detect_dissonance(text)
    if psc_engine is not None:
        psc_delta = _psc_dissonance_component(psc_engine)
        result["score"] = min(1.0, result["score"] + psc_delta)
        if psc_delta > 0:
            result["markers"].append("psc_predicted")
    return result
```

**Call site:** `cognitive_orchestrator.py` `assemble_prompt()` currently calls `detect_dissonance(message)`. Change to pass `psc_engine=self.workspace._psc_engine` if available.

---

### Step 5: Patch `memory.py` for DMU-Weighted Retrieval (Optional)

Current `DriftMemory.retrieve_context()` uses hybrid reranking (semantic + importance + recency). The DMU upgrade replaces the `_rerank()` logic with `DMURetriever`.

**Option A (Recommended):** Add DMU as an optional reranker.
```python
# In DriftMemory.__init__:
from drift.core.dmu import DMURetriever
try:
    from drift.core.psc_scaled import PSCBatchEngine
    self._dmu = DMURetriever(self.collection, psc_engine=None)
except ImportError:
    self._dmu = None

# In retrieve_context(), after raw Chroma results:
if self._dmu is not None and rerank:
    # Get embedding for query
    emb = self.embedding_function([query])[0]
    dmu_results = self._dmu.retrieve(emb, top_k=n_results)
    documents = [r["document"] for r in dmu_results]
    metadatas = [r["metadata"] for r in dmu_results]
else:
    # existing _rerank path
```

**Wire PSC:** In `global_workspace.py` after initializing both:
```python
if hasattr(self, '_psc_engine') and self._psc_engine is not None:
    if hasattr(being.memory, '_dmu') and being.memory._dmu is not None:
        being.memory._dmu.psc_engine = self._psc_engine
```

---

### Step 6: Update Tests & Verify

**Run baseline before any changes:**
```bash
cd /media/crexs/PortableSSD/drift/drift_repo_tmp
python -m pytest tests/ -q
```
Expected: This will likely fail due to broken `global_workspace.py`. Fix Step 0 first.

**After each V4 step, re-run:**
```bash
python -m pytest tests/ -q
python drift/core/security_defense_test.py  # if it exists
```

**Add V4 unit tests:** Copy `test_psc_scaled.py` from the zip into `tests/core/`.

---

## Work Breakdown & Estimates

| Task | Effort | Blocker |
|------|--------|---------|
| Step 0: Restore `global_workspace.py` | Medium | None |
| Step 1: Add core V4 files | Low | Step 0 |
| Step 2: Patch `being.py` snapshots | Low | Step 1 |
| Step 3: Patch `global_workspace.py` PSC | Medium | Step 0, 1 |
| Step 4: Patch `cognition.py` dissonance | Low | Step 1 |
| Step 5: Patch `memory.py` DMU | Medium | Step 1 |
| Step 6: Verify all 219+ tests | Medium | All above |

**Total estimated effort:** 1 focused session (~2-3 hours).

---

## Risk Register

| Risk | Mitigation |
|------|------------|
| `global_workspace.py` restoration changes behavior | Use `test_global_workspace.py` as exact spec; no creativity |
| FIELD_MAP missing fields | Graceful fallback to 0.5 for missing dimensions |
| PSC adds latency | Benchmarked at ~290µs; negligible vs Gemini inference |
| DMU diversity floor breaks memory quality | Cap at 40% per category; monitor retrieval relevance |
| Test regression below 219 | Run full suite after every file change |
| Cyber boundary violation | No changes to `brain.py` or `security_tools.py` |

---

## Files to Touch

```
drift/core/global_workspace.py    ← RESTORE + PSC integration
drift/core/being.py               ← Snapshot hook
drift/core/cognition.py           ← Optional PSC dissonance
drift/core/memory.py              ← Optional DMU reranking
drift/core/psc_scaled.py          ← NEW (from zip)
drift/core/being_snapshot.py      ← NEW (from zip)
drift/core/dmu.py                 ← NEW (from zip)
tests/core/test_psc_scaled.py     ← NEW (from zip)
```

---

## Decision Needed from You

1. **Should I proceed with Step 0 (restoring `global_workspace.py`) first?** The existing codebase appears to have a corrupted/incomplete GWT implementation. Without fixing this, V4 integration has no stable foundation.

2. **PSC Policy default:** `BALANCED` (0.55 threshold) for normal use, or `SECURITY` (0.44) since you do active bug bounty work?

3. **DMU integration depth:** Full Option A (replace `_rerank` with DMU) or minimal Option B (external wrapper only)?

4. **Should I execute this plan now, or do you want to review/modify first?**
