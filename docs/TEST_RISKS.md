# Test Suite Risk Analysis

**Scope:** INFJ Bot + DRIFT Hive Mind test suite (47 test files, ~600+ assertions)
**Last updated:** 2026-05-08
**Status:** Active — risks flagged, mitigation in progress

---

## Executive Summary

The test suite provides broad module coverage but carries significant **false-confidence** risk. Most tests validate "happy path" behavior and output shape, while error handling, concurrency, data integrity, and production-fidelity gaps remain largely unexercised. The heaviest risks cluster around:

1. **SQLite persistence** — temp DBs differ from production; teardown unverified
2. **Probabilistic features** — frequency-based assertions can flake in CI
3. **Mock saturation** — LLM, network, and browser paths are fully mocked
4. **Private API coupling** — tests call `_private_methods()`, creating brittle contracts
5. **No failure-mode coverage** — disk full, corruption, permission denied, race conditions

---

## Risk Matrix

| ID | Risk | Severity | Likelihood | Files Affected | Mitigation Status |
|----|------|----------|------------|----------------|-------------------|
| R1 | Tempfile cleanup failures on Windows | Medium | Medium | `test_global_workspace.py`, most DB tests | Open |
| R2 | DB state assumptions untested | High | High | `test_global_workspace.py`, `test_being.py`, `test_shadow.py` | Open |
| R3 | No error handling / failure mode tests | High | High | All DB-backed modules | Open |
| R4 | Private method coupling | Medium | Medium | `test_global_workspace.py`, `test_stress.py` | Open |
| R5 | Data integrity gaps (duplicates, corruption) | High | Medium | `test_global_workspace.py`, `test_self_modify.py` | Open |
| R6 | False confidence from weak assertions | Medium | High | `test_bot.py`, `test_stress.py`, `test_persona.py` | Open |
| R7 | Production environment mismatch | Medium | Medium | All tests using `tempfile` | Open |
| R8 | Probabilistic test flakiness | Medium | Low | `test_shadow.py`, `test_being.py`, `test_explorer.py` | Open |
| R9 | Missing module coverage | High | High | `brain.py`, `commands.py`, `web_app.py`, `emailer.py`, `rate_limit.py` | Open |
| R10 | No concurrency / race condition tests | High | Low | `test_global_workspace.py`, `test_self_modify.py`, `hive_mind/tests/` | Open |

---

## Detailed Risk Breakdown

### R1 — Test Environment Dependencies (Tempfile Behavior)

**Description:**
Tests rely on `tempfile.NamedTemporaryFile()` and `tempfile.TemporaryDirectory()` for isolated SQLite databases. On Windows, these behave differently:
- `delete=False` files cannot be unlinked while open (SQLite holds a handle)
- Path separators differ (`\` vs `/`)
- WAL mode creates `-wal` and `-shm` sidecars that may not clean up

**Evidence:**
```python
# test_global_workspace.py:30-37
with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
    path = tmp.name
# ... test runs ...
finally:
    _unlink_workspace_db_files(path)  # Custom cleanup; no assertion it succeeded
```

**Impact:** CI flakiness on Windows; orphaned DB files consuming disk.

**Mitigation:**
- Use `tmp_path` pytest fixture (cross-platform, auto-cleanup)
- Assert cleanup succeeded in teardown
- Add Windows-specific CI runner

---

### R2 — Database State Assumptions

**Description:**
Tests assume clean initialization states without verifying them. If a module's default values change, tests may pass with silently wrong data.

**Evidence:**
```python
# test_global_workspace.py — no test for default cycle_count
def test_cycle_count_persistence():
    # Assumes GlobalWorkspace initializes with cycle_count=0
    # but never asserts it
```

Other examples:
- `test_being.py` assumes `energy=1.0` on init without asserting
- `test_shadow.py` assumes `suppress()` creates DB rows without checking count

**Impact:** Regressions in initialization logic go undetected.

**Mitigation:**
- Add explicit default-state assertions to every test class
- Use schema-validation helpers

---

### R3 — Incomplete Error Handling Coverage

**Description:**
Zero tests exercise failure modes: invalid `db_path`, read-only filesystem, corrupted SQLite, disk full, or concurrent access.

**Evidence:**
- No test for `GlobalWorkspace(db_path="/nonexistent/path/db.sqlite")`
- No test for read-only `chmod 555` temp directory
- No test for corrupt DB header (only `test_shadow.py` has one corruption test)
- No test for `sqlite3.OperationalError: database is locked`

**Impact:** Production failures (permissions, disk space, corruption) have no tested recovery paths.

**Mitigation:**
- Add `test_failure_modes.py` with parameterized error injection
- Test corrupt-header recovery
- Test read-only fallback behavior

---

### R4 — API Contract Risks (Private Method Coupling)

**Description:**
Tests directly invoke `_private_methods()` and rely on internal field names, creating tight coupling to implementation details.

**Evidence:**
```python
# test_global_workspace.py:101
old_content.timestamp = "2020-01-01T00:00:00"  # Direct field mutation

# test_stress.py (multiple locations)
ws._save_state()  # Direct private method call

# test_bot.py
brain._generate(...)  # Private via MagicMock
```

**Impact:** Refactoring internals breaks multiple tests simultaneously, even when public API is unchanged.

**Mitigation:**
- Refactor tests to use public APIs only
- Where private access is unavoidable, document the contract and add integration tests

---

### R5 — Data Integrity Gaps

**Description:**
Tests verify existence of data but not correctness, uniqueness, or absence of side effects.

**Evidence:**
```python
# test_global_workspace.py — only checks one record
def test_competition_saves_to_db():
    # ... compete ...
    history = ws.get_history()
    assert len(history) == 1  # But what if duplicate entries were created?
```

Other gaps:
- No verification that `compete()` doesn't mutate non-winning broadcasts
- No test for extremely large salience values (`float('inf')`, negative)
- No test for special characters in content (Unicode, null bytes, SQL injection)

**Impact:** Data corruption (duplicates, injection, overflow) goes undetected.

**Mitigation:**
- Add duplicate-detection assertions
- Fuzz content with special characters
- Add boundary-value tests for numeric fields

---

### R6 — False Confidence from Weak Assertions

**Description:**
Many tests assert only that methods "don't crash" or that output contains a substring, which can pass with incorrect data.

**Evidence:**
```python
# test_global_workspace.py
assert "test_content" in history[0]["content"]  # Substring match — could be partial

# test_bot.py
assert result is not None  # Non-crash assertion only

# test_stress.py
assert removed >= 0  # Always true
```

**Impact:** Tests give green CI while bugs slip through.

**Mitigation:**
- Replace substring checks with exact or structured assertions
- Validate output shape, types, and bounds, not just existence

---

### R7 — Production Environment Mismatch

**Description:**
Tests use isolated temp databases with single-file SQLite, while production may use:
- ChromaDB persistent directories on external SSDs
- WAL mode with `-wal`/`-shm` sidecars
- Larger datasets (10K+ memories)
- Concurrent access from web app + CLI + scheduler

**Evidence:**
- All DB tests use `tempfile.NamedTemporaryFile` — not ChromaDB
- `test_embeddings.py` uses small test sentences, not real document chunks
- `test_stress.py` runs 100 rapid writes — still tiny vs production scale

**Impact:** Performance regressions and scale-dependent bugs manifest only in production.

**Mitigation:**
- Add a `test_production_smoke.py` that runs against `INFJ_DATA_DIR`
- Add load tests with 10K+ record datasets
- Add concurrent-access stress tests

---

### R8 — Probabilistic Test Flakiness

**Description:**
Several features use randomness (thought sharing, exploration, shadow surfacing). Tests use frequency-based assertions over many iterations, which can fail probabilistically.

**Evidence:**
```python
# test_being.py
shares = sum(being.should_share_thought() for _ in range(100))
assert shares > 10  # ~11% chance — could legitimately be 9

# test_shadow.py
for _ in range(50):
    if shadow.surface(stress=1.0):
        surfaced += 1
assert surfaced > 0  # 50 trials at ~10% = ~0.5% false-negative rate
```

**Impact:** CI flakes waste time and erode trust in the test suite.

**Mitigation:**
- Seed RNG in tests: `random.seed(42)`
- Use deterministic test doubles where possible
- Increase trial counts or use statistical bounds (Clopper-Pearson)

---

### R9 — Missing Module Coverage

**Description:**
Several critical modules have zero or near-zero dedicated test coverage.

| Module | Test File | Coverage Level | Risk |
|--------|-----------|---------------|------|
| `brain.py` | None | 0% | **Critical** — core inference |
| `commands.py` | `test_bot.py` (indirect) | ~10% | **High** — 40+ commands |
| `web_app.py` | `test_bot.py` (2 tests) | ~5% | **High** — public API surface |
| `emailer.py` | None | 0% | **Medium** — SMTP/Gmail |
| `rate_limit.py` | None | 0% | **Medium** — new file |
| `maintenance.py` | None | 0% | **Medium** — new file |
| `memory_reliability.py` | None | 0% | **Medium** — trust scoring |
| `api.py` | `test_bot.py` (2 tests) | ~10% | **Medium** |
| `drift.py` | None | 0% | **Medium** — main orchestrator |
| `tui.py` | None | 0% | **Low** — interactive only |

**Impact:** Refactoring or extending these modules has no safety net.

**Mitigation:**
- Prioritize `brain.py` and `commands.py` tests
- Add FastAPI TestClient tests for `web_app.py`
- Add mock-SMTP tests for `emailer.py`

---

### R10 — No Concurrency / Race Condition Tests

**Description:**
SQLite is accessed from multiple contexts (web app, scheduler, CLI, hive mind), but no tests verify thread safety or race condition handling.

**Evidence:**
- `test_global_workspace.py` — single-threaded only
- `test_self_modify.py` — no concurrent proposal creation
- `hive_mind/tests/` — no split-brain or partition tests
- `test_stress.py` — concurrent memory writes but no assertion on consistency

**Impact:** Race conditions in production cause data corruption or crashes.

**Mitigation:**
- Add `threading`/`asyncio` concurrent-access tests
- Add SQLite `timeout` and `isolation_level` validation
- Add Hive Mind Byzantine-fault tests

---

## Recommended Mitigation Roadmap

### Phase 1 — Immediate (This Sprint)
- [ ] Fix `test_global_workspace.py` with `tmp_path` fixture and cleanup assertions
- [ ] Add default-state validation to all DB-backed test classes
- [ ] Seed RNG in probabilistic tests (`random.seed(42)`)
- [ ] Add `test_rate_limit.py` and `test_maintenance.py` for new modules

### Phase 2 — Short Term (Next 2 Weeks)
- [ ] Create `tests/test_failure_modes.py` with error injection
- [ ] Refactor private-method tests to use public APIs where possible
- [ ] Add duplicate-detection and boundary-value assertions
- [ ] Add `test_brain_smoke.py` with mocked LLM client

### Phase 3 — Medium Term (Next Month)
- [ ] Add production-smoke tests against `INFJ_DATA_DIR`
- [ ] Add concurrent-access stress tests (10 threads, 100 ops each)
- [ ] Add Windows CI runner
- [ ] Add load tests with 10K+ ChromaDB records

---

## Appendix: Files by Risk Category

### High Risk (needs immediate attention)
- `tests/test_global_workspace.py` — R1, R2, R3, R4, R5, R7
- `brain.py` — R9 (no tests at all)
- `commands.py` — R9 (no dedicated tests)
- `web_app.py` — R9 (minimal coverage)

### Medium Risk (should address in Phase 2)
- `tests/test_shadow.py` — R8 (probabilistic)
- `tests/test_being.py` — R8 (probabilistic)
- `tests/test_explorer.py` — R8 (probabilistic)
- `tests/test_stress.py` — R6 (weak assertions), R7 (scale mismatch)
- `tests/test_bot.py` — R6 (weak assertions), R4 (private methods)

### Lower Risk (monitor)
- `hive_mind/tests/` — R10 (concurrency), but basic coverage is solid
- `tests/test_embeddings.py` — R7 (small test data), but well-structured
