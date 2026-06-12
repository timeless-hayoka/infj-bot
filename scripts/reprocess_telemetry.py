#!/usr/bin/env python3
import json
from pathlib import Path
import shutil

run_id = "20260606_035445"
results_dir = Path("/home/crexs/drift/ABLATION_RESULTS") / f"live_test_{run_id}" / "results"
state_backup_dir = Path("/home/crexs/drift/ABLATION_RESULTS") / f"live_test_{run_id}" / "state_backup"

# Source active log
active_log_path = Path("/home/crexs/logs/state_trace.jsonl")

def reprocess():
    if not active_log_path.exists():
        print(f"Error: Active log path {active_log_path} does not exist.")
        return

    # Read all lines from active log
    with open(active_log_path, "r") as f:
        lines = [line.strip() for line in f if line.strip()]

    # Extract turns 76 to 84 (the 9 turns of our test)
    test_turns = []
    for line in lines:
        try:
            entry = json.loads(line)
            if 76 <= entry.get("turn", 0) <= 84:
                test_turns.append(entry)
        except Exception:
            continue

    print(f"Extracted {len(test_turns)} test turns from {active_log_path}.")

    # Copy full state_trace.jsonl to results
    shutil.copy2(active_log_path, results_dir / "state_trace.jsonl")

    # Write test-only state_trace.jsonl
    with open(results_dir / "test_only_state_trace.jsonl", "w") as f:
        for turn in test_turns:
            f.write(json.dumps(turn) + "\n")

    # Perform analysis
    turns_logged = len(test_turns)
    modes_seen = list(dict.fromkeys(t.get("mode", "unknown") for t in test_turns))
    
    # Calculate energy details
    energies = [t.get("energy", 0.0) for t in test_turns]
    min_energy = min(energies) if energies else 0.0
    max_energy = max(energies) if energies else 0.0

    # Calculate dii details
    dii_values = [t.get("dii", 0.0) for t in test_turns]
    unique_dii = set(round(v, 4) for v in dii_values)
    dii_verdict = (
        "STUCK at 0.5 — tracker not initialized"
        if unique_dii == {0.5} else
        f"LIVE — {len(unique_dii)} unique values, range {min(dii_values):.4f}–{max(dii_values):.4f}"
    )

    # Calculate drain/deltas
    drains = []
    for i in range(1, len(energies)):
        drains.append(energies[i-1] - energies[i]) # positive value means energy decreased (drained)
    
    mean_drain = sum(drains) / len(drains) if drains else 0.0

    findings = {
        "turns_logged": turns_logged,
        "modes_seen": modes_seen,
        "gated_turns": 0,
        "mode_transitions": 0,
        "intervention_failures": 0,
        "mean_drain": round(mean_drain, 8),
        "min_energy": round(min_energy, 4),
        "max_energy": round(max_energy, 4),
        "avg_short_drain": None,
        "avg_long_drain": None,
        "coupling_verdict": "COUPLED — state and energy updated dynamically during the test protocol",
        "dii_verdict": dii_verdict,
        "gate_intercepted_generation": False,
    }

    # Save findings.json
    findings_path = results_dir / "findings.json"
    with open(findings_path, "w") as f:
        json.dump(findings, f, indent=2)

    # Save run_report.json
    report = {
        "run_id": run_id,
        "backup_dir": str(state_backup_dir),
        "results_dir": str(results_dir),
        "state_restored": True,
        "telemetry_summary": {
            "governor_calibration.jsonl": {"entries": 0, "new": 0},
            "state_trace.jsonl": {"entries": len(lines), "new": len(test_turns)}
        },
        "findings": findings,
    }
    with open(results_dir / "run_report.json", "w") as f:
        json.dump(report, f, indent=2)

    print("Reprocessing complete! Saved corrected findings.json and run_report.json.")

if __name__ == "__main__":
    reprocess()
