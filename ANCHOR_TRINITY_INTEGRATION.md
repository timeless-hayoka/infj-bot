# Trinity ↔ ANCHOR Integration Guide

## Architecture

### ANCHOR's Event-Driven Registry

ANCHOR uses an event stream to track each case from detection → correlation → reproduction:

```
Run created
  ├─ case.started
  ├─ finding.detected (swc detected)
  ├─ finding.correlated (multiple tools agree)
  └─ poc.result (exploit_verified=True/False) ← Trinity submits here
     └─ Case promoted to REPRODUCED_REAL or marked FAILED
```

### Data Flow

```
Trinity                           ANCHOR
├─ Propose hypothesis        →  Create run: create_run(mode="trinity", ...)
├─ Generate PoC              →  (asynchronously)
├─ Execute PoC (Forge)       →  (Trinity or external executor)
├─ Validate result           →  emit("poc.result", { exploit_verified: T/F, ... })
│                                └─ _apply_event() updates case state
└─ Check registry            ←  run_registry(run_id) → final case list
```

---

## ANCHOR's Run & Case Structure

### Run Class (`anchor_server.py:310`)

```python
@dataclass
class Run:
    run_id: str                           # "run_abc123def456"
    benchmark: str                        # Benchmark ID (usually "3a8b8bf0")
    mode: str                             # "demo" | "trinity" | "hunt_analysis"
    params: dict[str, Any]                # {"target": "...", "script": "...", "registry": "..."}
    status: str                           # "pending" | "running" | "done"
    cases: dict[str, dict[str, Any]]      # case_id → case object
    registry: dict[str, Any] | None       # Final aggregated registry
    events: list[dict[str, Any]]          # All events emitted
```

### Case Object Structure

```python
case = {
    "case_id": "TinyReentrancy",          # Unique case ID
    "contract": "TinyReentrancy",         # Contract being tested
    "swc": "SWC-107",                     # Primary SWC weakness
    "expected": ["SWC-107"],              # Expected weaknesses
    "detected": ["SWC-107"],              # Detected by scanner
    "correlated": ["SWC-107"],            # Correlated by multiple tools
    "reproduced_real": ["SWC-107"],       # Reproduced with real PoC
    "validation_state": "REPRODUCED_REAL", # PENDING | DETECTED | CORRELATED | FAILED | REPRODUCED_REAL
    "reproduction_status": "REPRODUCED_REAL", # Human-readable status
    "execution_artifacts": [              # List of PoC results
        {
            "swc": "SWC-107",
            "success": True,
            "exploit_verified": True,
            "assertion_count": 3,
            "test_path": "test/TinyReentrancy.t.sol",
            "stderr": "",
            "failure_reason": "",
        }
    ],
    "timestamp": "2026-07-25T18:00:00Z",
}
```

### Registry Object (Final Output)

```python
registry = {
    "schema_version": "1.0",
    "kind": "anchor.registry",
    "benchmark_id": "3a8b8bf0",
    "generated_at": "2026-07-25T18:05:00Z",
    "total": 10,                          # Total cases tested
    "reproduced": 9,                      # Cases that reached REPRODUCED_REAL
    "precision": 0.90,                    # TP / (TP + FP)
    "recall": 0.90,                       # TP / (TP + FN)
    "f1": 0.90,                           # Harmonic mean
    "results": [/* list of case objects */],
}
```

---

## Trinity's Integration Points

### 1. Create a Run

```python
import asyncio
from anchor_server import create_run

# Create a new ANCHOR run in "trinity" mode
run = create_run(
    mode="trinity",
    script="trinity_hunt.py",            # Path to Trinity script
    registry="trinity_findings.json",     # Where to save findings
    benchmark="3a8b8bf0",                 # Use this benchmark ID
    target="src/TinyReentrancy.sol",      # Optional: limit to one contract
)
run_id = run.run_id
print(f"Created run: {run_id}")

# Store run globally for reference
ANCHOR_RUNS[run_id] = run
```

### 2. Emit Events as Trinity Investigates

```python
# When Trinity detects a weakness
await run.emit("finding.detected", {
    "case_id": "reentrancy_case_1",
    "contract": "TinyReentrancy",
    "swc": "SWC-107",
    "expected": ["SWC-107"],
    "timestamp": "2026-07-25T18:01:00Z",
})

# When Trinity correlates evidence (multiple tools agree)
await run.emit("finding.correlated", {
    "case_id": "reentrancy_case_1",
    "swc": "SWC-107",
})

# When Trinity executes a PoC and gets results
await run.emit("poc.result", {
    "case_id": "reentrancy_case_1",
    "swc": "SWC-107",
    "exploit_verified": True,            # ← THE CRITICAL FLAG
    "assertion_count": 3,
    "test_path": "test/TinyReentrancy.t.sol",
    "stderr": "",
    "failure_reason": "",
})
```

### 3. Check Results

```python
# Get the final registry (list of all cases with results)
from anchor_server import run_registry

registry = await run_registry(run_id)
print(f"Total cases: {registry['total']}")
print(f"Reproduced: {registry['reproduced']}")
print(f"Precision: {registry['precision']}")

# Get a specific case
for case in registry["results"]:
    if case["validation_state"] == "REPRODUCED_REAL":
        print(f"✓ {case['case_id']} ({case['swc']}): {case['reproduction_status']}")
    else:
        print(f"✗ {case['case_id']}: {case['validation_state']}")
```

---

## Event Payload Schemas

### `poc.result` (Trinity → ANCHOR)

**Critical: This is how Trinity tells ANCHOR a PoC succeeded**

```python
{
    "case_id": str,                  # Unique case identifier
    "swc": str | None,               # SWC code (e.g., "SWC-107")
    "exploit_verified": bool,        # TRUE = REPRODUCED_REAL, FALSE = FAILED
    "assertion_count": int,          # Number of assertions that passed
    "test_path": str | None,         # Path to Forge test file
    "stderr": str,                   # Any error output
    "failure_reason": str,           # Human explanation if failed
}
```

When ANCHOR receives `poc.result`:
- If `exploit_verified=True` → case state = "REPRODUCED_REAL"
- If `exploit_verified=False` → case state = "FAILED"

### `case.started`

```python
{
    "case_id": str,
    "contract": str | None,
    "expected": list[str],           # SWC codes expected in this contract
    "timestamp": str,                # ISO timestamp
}
```

### `finding.detected`

```python
{
    "case_id": str,
    "contract": str | None,
    "swc": str,                      # Detected SWC
    "expected": list[str],
}
```

### `finding.correlated`

```python
{
    "case_id": str,
    "swc": str,                      # SWC confirmed by multiple tools
}
```

---

## Integration Pattern in Trinity Code

```python
# trinity_hunt.py or similar

async def hunt_with_anchor_registry(
    run: Run,
    hypotheses: list[Hypothesis],
) -> dict[str, Any]:
    """Run Trinity's hunt loop, emitting ANCHOR events."""
    
    async with run.lock:  # Thread-safe access
        await run.emit("run.started", {
            "timestamp": utc_stamp(),
            "script": "trinity_hunt.py",
        })
    
    for hypothesis in hypotheses:
        case_id = hypothesis.id
        
        # Start the case
        async with run.lock:
            await run.emit("case.started", {
                "case_id": case_id,
                "contract": hypothesis.contract,
                "expected": [hypothesis.swc],
            })
        
        # Trinity detects it
        async with run.lock:
            await run.emit("finding.detected", {
                "case_id": case_id,
                "swc": hypothesis.swc,
                "expected": [hypothesis.swc],
            })
        
        # Trinity correlates it
        async with run.lock:
            await run.emit("finding.correlated", {
                "case_id": case_id,
                "swc": hypothesis.swc,
            })
        
        # Trinity generates and executes PoC
        poc_code = generate_poc(hypothesis)
        forge_result = await execute_forge(poc_code, hypothesis.contract)
        
        # Trinity tells ANCHOR the result
        async with run.lock:
            await run.emit("poc.result", {
                "case_id": case_id,
                "swc": hypothesis.swc,
                "exploit_verified": forge_result.all_assertions_passed,
                "assertion_count": forge_result.passed_assertions,
                "test_path": forge_result.test_file,
                "stderr": forge_result.stderr,
                "failure_reason": forge_result.error_msg or "",
            })
    
    # Done with this hunt run
    async with run.lock:
        await run.emit("run.completed", {
            "timestamp": utc_stamp(),
        })
    
    # Return the final registry
    return build_registry_from_cases(run)
```

---

## Key Data Points Trinity Must Track

For `poc.result` to work correctly, Trinity needs to extract from Forge execution:

1. **`exploit_verified`** (bool) — ALL assertions passed? (Critical for REPRODUCED_REAL promotion)
2. **`assertion_count`** (int) — How many assertions passed?
3. **`test_path`** (str) — Path to the test file
4. **`stderr`** (str) — Any compiler/runtime errors
5. **`failure_reason`** (str) — Human description of why it failed (if it did)

---

## Validation Hierarchy

ANCHOR's `LADDER` tracks progression:

```python
LADDER = {
    "DETECTED": 0,           # Scanner found a potential issue
    "CORRELATED": 1,         # Multiple tools or stages confirm it
    "REPRODUCED_REAL": 2,    # PoC executed, assertions passed, state delta measured
}
```

Trinity moves cases up the ladder by emitting events. Only `poc.result` with `exploit_verified=True` reaches level 2.

---

## Async/Await Requirements

ANCHOR's `Run.emit()` is **async**:

```python
async def emit(self, type_: str, payload: dict[str, Any]) -> dict[str, Any]:
    event = self._event(type_, payload)
    await self.publish(event, terminal=type_ in TERMINAL_EVENTS)
    return event
```

Trinity must either:
1. Run in an async context and `await run.emit(...)`
2. Use `asyncio.run()` or `asyncio.create_task()` if not already async
3. Call `run.publish()` synchronously if you bypass `emit()` (not recommended)

---

## Files to Reference

- **`anchor_server.py`** — Run class, event emission, case state machine
- **`evidence_schema.py`** — EvidenceRecord structure, proof gate
- **`outcome_evidence.py`** — Evidence normalization and insights
- **`anchor_cli.py`** — How to load and display results

---

## Success Criteria

When Trinity is fully integrated:

```python
# 1. Create a Trinity run
run = create_run(mode="trinity", script="trinity_hunt.py")

# 2. Trinity emits events for each case it investigates
await run.emit("poc.result", { "exploit_verified": True, ... })

# 3. ANCHOR's case state updates automatically
assert run.cases["case_id"]["validation_state"] == "REPRODUCED_REAL"

# 4. Final registry shows proper metrics
registry = build_registry_from_cases(run)
assert registry["reproduced"] == <number of REPRODUCED_REAL cases>
assert registry["precision"] == <TP / (TP + FP)>
```

---

## Next Steps

1. **Phase 1**: Import and read ANCHOR's modules in Trinity
2. **Phase 2**: Modify Trinity's PoC execution to create an ANCHOR run
3. **Phase 3**: Replace Trinity's local scoring with `poc.result` events
4. **Phase 4**: Test with 10-contract tranche (6 vulnerable + 4 safe)
5. **Phase 5**: Validate metrics match expected TP/FP/FN/TN counts
