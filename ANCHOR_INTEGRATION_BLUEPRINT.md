# Trinity ↔ ANCHOR Integration Blueprint

## Current State

### ANCHOR's Validation Architecture
ANCHOR is already a complete validation engine with:

**Proof Gate** (`evidence_schema.py:130-137`)
```python
def bugbot_proof_gate_status(*, total: int, passed: int, failed: int) -> str:
    # Passes ONLY if: total > 0 AND failed == 0 AND passed == total
    # All proofs must pass, no failures allowed
```

**Validation Hierarchy** (`anchor_server.py:50`)
```python
LADDER = {
    "DETECTED": 0,           # Scanner found it
    "CORRELATED": 1,         # Multiple tools agree / hypothesis formed
    "REPRODUCED_REAL": 2     # PoC executed with runtime state delta + assertions passed
}
```

**Evidence Record Structure** (`evidence_schema.py:44-54`)
```python
@dataclass
class EvidenceRecord:
    schema_version: str          # "1.0"
    kind: str                    # "benchmark" | "bugbot_training" | "hunt_analysis"
    artifact_path: str           # Path to JSON proof file
    timestamp: str               # ISO timestamp
    target: str                  # Contract or scenario identifier
    run_id: str                  # Unique run ID
    status: str                  # proof_gate_passed | proof_gate_failed | published | rejected | unknown
    metrics: dict[str, Any]      # Total, passed, failed, proofs[], reproduction_rate, precision, recall
    links: dict[str, str]        # artifact_json, metrics_json, record paths
    source: dict[str, Any]       # benchmark_id, level, runner, scenario_pack, final_status
```

**Evidence Statuses** (`evidence_schema.py:13-20`)
- `proof_gate_passed`: All assertions + PoC execution succeeded
- `proof_gate_failed`: Any assertion failed or PoC crashed
- `published`: Benchmark with no failures/timeouts
- `rejected`: Benchmark with failures/timeouts or analysis marked FAILED
- `unknown`: Indeterminate

### ANCHOR's Proof Hierarchy for Benchmarks
1. **raw_status** = "complete" | "published" | "scaffold" → Check metrics
2. If **failed** == 0 AND **timed_out** == 0 → `status = "published"` (REPRODUCED_REAL)
3. Else → `status = "rejected"` (POC_EXECUTED_UNPROVEN)

### ANCHOR's Runtime State Tracking
Benchmarks track:
- `metrics.total` — Total PoC test cases
- `metrics.passed` — Passed assertions
- `metrics.failed` — Failed assertions  
- `metrics.timed_out` — Timeouts
- `metrics.skipped` — Skipped
- `metrics.reproduction_rate` — passed / total
- `metrics.precision` — True positives / (TP + FP)
- `metrics.recall` — True positives / (TP + FN)

No explicit "state_delta" field, but **reproduction_rate > 0** implies runtime proof execution.

---

## Trinity's Role (Hunter)

Trinity should:
1. **Propose hypotheses** — Attack path reasoning, correlation of findings
2. **Generate PoCs** — Forge test strategies, payload crafting
3. **Ask ANCHOR to validate** — Submit PoC + hypothesis to ANCHOR's proof gate
4. **React to verdicts** — Reframe failed attempts, choose next investigation path
5. **Manage research flow** — Decide when to pivot, when to go deeper

Trinity does **NOT**:
- Execute Forge tests (ANCHOR does)
- Validate assertions (ANCHOR does)
- Measure runtime state (ANCHOR does)
- Calculate metrics (ANCHOR does)
- Decide what counts as "real" (ANCHOR does)

---

## The Integration Interface

### Trinity → ANCHOR (Proposed Call)

```python
# Trinity wants ANCHOR to validate a hypothesis
verdict = anchor.validate_poc(
    hypothesis={
        "swc": "SWC-107",           # Weakness class
        "title": "Reentrancy via fallback",
        "breach_step": "Call target with state unchecked",
        "attack_path": ["external call", "callback", "state mutation"],
    },
    poc_code={
        "forge_test_path": "test/TinyReentrancy.t.sol",
        "test_contract": "TinyReentrancyTest",
        "target_contract": "TinyReentrancy",
    },
    contract_path="src/TinyReentrancy.sol",
    timestamp="2026-07-25T18:00:00Z",
)
```

### ANCHOR → Trinity (Verdict)

```python
verdict = {
    "validation_state": "REPRODUCED_REAL",  # or "POC_EXECUTED_UNPROVEN" | "POC_INVALID"
    "outcome_evidence": {
        "schema_version": "1.0",
        "kind": "hunt_analysis",
        "artifact_path": "outcomes/hunt/reentrancy_hunt_001.json",
        "timestamp": "2026-07-25T18:05:00Z",
        "target": "TinyReentrancy",
        "run_id": "reentrancy_hunt_001",
        "status": "published",  # Proof gate passed
        "metrics": {
            "total": 3,
            "passed": 3,
            "failed": 0,
            "skipped": 0,
            "reproduction_rate": 1.0,
            "precision": 1.0,
            "recall": 1.0,
        },
        "links": {
            "forge_output": "outcomes/hunt/reentrancy_hunt_001_forge.json",
        },
        "source": {
            "forge_status": "complete",
            "final_status": "PASS",
        },
    },
    "reproduction_status": "REPRODUCED_REAL",
    "error_reason": None,
}
```

---

## Trinity's Decision Logic (Post-Verdict)

```python
if verdict["validation_state"] == "REPRODUCED_REAL":
    # Champion! Register finding
    registry.promote(
        finding=hypothesis,
        evidence=verdict["outcome_evidence"],
        confidence="HIGH",
    )
    current_target.mark_as_exploited()

elif verdict["validation_state"] == "POC_EXECUTED_UNPROVEN":
    # PoC ran but assertions failed
    # Options:
    # 1. Refine the breach step
    # 2. Try a different attack angle
    # 3. Add more pre-conditions
    investigator.reframe_hypothesis(hypothesis, failure_mode="assertions_failed")

elif verdict["validation_state"] == "POC_INVALID":
    # PoC didn't execute (compile error, bad target, etc)
    investigator.discard_hypothesis(hypothesis)
```

---

## Implementation Steps

### Phase 1: Read ANCHOR's Case State (This Week)
- [ ] Read `anchor_server.py` for existing registry structure
- [ ] Understand how ANCHOR stores/retrieves case files
- [ ] Identify the validation entry point (how ANCHOR receives PoCs)

### Phase 2: Strip Trinity's Local Scorer
- [ ] Remove `score_poc()` from Trinity  
- [ ] Remove `final_state`, `evidence` local tracking
- [ ] Remove the manual "REPRODUCED_REAL" logic

### Phase 3: Call ANCHOR's Validator
- [ ] Import ANCHOR's validation module
- [ ] Replace Trinity's scoring with: `verdict = anchor.validate_poc(...)`
- [ ] Map Trinity's hypothesis → ANCHOR's expected input shape
- [ ] Parse `verdict` and update Trinity's investigation flow

### Phase 4: Build the Registry Bridge
- [ ] Connect Trinity's registry to ANCHOR's evidence records
- [ ] Ensure Trinity's CSV/JSON output references ANCHOR's canonical evidence paths
- [ ] Add TP/FP/FN/TN calculation from ANCHOR metrics

### Phase 5: Run 10-Contract Tranche
- [ ] 6 vulnerable + 4 safe contracts
- [ ] Validate all via ANCHOR
- [ ] Measure TP = X, FP = 0, TN = 4, FN = (6 - X)

---

## Key Files to Understand

1. **`evidence_schema.py`** — EvidenceRecord structure, proof gate, status normalization
2. **`outcome_evidence.py`** — Evidence collection and normalization
3. **`anchor_server.py`** — Registry, PoC execution, result aggregation
4. **`anchor_cli.py`** — CLI entry point (read status_score, result rendering)
5. **`anchor_strategy.py`** — Strategy selection (how ANCHOR chooses next steps)

---

## Design Principle

**Trinity hunts. ANCHOR judges.**

Trinity can suspect anything. ANCHOR decides what counts as proof.

Separation of concerns:
- **Reasoning** (Trinity) stays fast and creative
- **Validation** (ANCHOR) stays strict and auditable
- **Registry** (unified) keeps one source of truth

---

## Why This Works

1. **No rebuild** — ANCHOR already has a proven validation pipeline
2. **No duplication** — Trinity focuses on hypothesis generation, not scoring
3. **Audit trail** — Every finding has ANCHOR's canonicalized evidence
4. **Per-SWC scoring** — Metrics are scoped to each weakness class
5. **Negative controls** — ANCHOR's benchmark mode handles safe vs vulnerable contracts
6. **Reproducibility** — PoC artifacts live in ANCHOR's outcomes directory
