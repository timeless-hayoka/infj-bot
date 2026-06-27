#!/usr/bin/env python3
"""
The Forge V5: Patch-Aware Validation & Delta Gate System
Usage: forge_verify_patch.py <target_directory> <patch_file> <mode:fast|deep>

Flow:
1. Snapshot Baseline
2. Apply Patch
3. Snapshot Post-Patch
4. Delta Analysis (Approve/Reject/Rollback)
"""

import os
import sys
import json
import subprocess
import shutil
from pathlib import Path
from datetime import datetime

def run_validator(target_dir: str, mode: str) -> dict:
    env = os.environ.copy()
    env["FORGE_JSON_OUTPUT"] = "1"
    res = subprocess.run(
        ["/home/crexs/infj_bot/10_step_validator.py", target_dir, mode],
        capture_output=True, text=True, env=env
    )
    if not res.stdout.strip():
        print("ERROR: Validator produced no output. Stderr:", res.stderr)
        return {}
    try:
        return json.loads(res.stdout)
    except json.JSONDecodeError:
        print("ERROR: Failed to parse validator output as JSON. Output:", res.stdout)
        return {}

def extract_signatures(report: dict) -> dict:
    signatures = {}
    for lang, data in report.items():
        for sig in data.get("signatures", []):
            signatures[sig["file"]] = sig
    return signatures

def apply_patch(target_dir: str, patch_file: str) -> bool:
    print(f"Applying patch {patch_file} to {target_dir}...")
    res = subprocess.run(["patch", "-p1", "-d", target_dir, "-i", patch_file], capture_output=True, text=True)
    if res.returncode != 0:
        print("Failed to apply patch!")
        print(res.stdout)
        print(res.stderr)
        return False
    return True

def rollback_patch(target_dir: str, patch_file: str):
    print("Rolling back patch...")
    subprocess.run(["patch", "-p1", "-R", "-d", target_dir, "-i", patch_file], capture_output=True, text=True)

def main():
    if len(sys.argv) < 3:
        print("Usage: forge_verify_patch.py <target_directory> <patch_file> [mode:fast|deep]")
        sys.exit(1)

    target_dir = sys.argv[1]
    patch_file = os.path.abspath(sys.argv[2])
    mode = sys.argv[3] if len(sys.argv) > 3 else "deep"

    print("="*50)
    print("🔥 FORGE DELTA GATE: PATCH VALIDATION SYSTEM")
    print("="*50)

    # 1. Snapshot Baseline
    print("\n📸 [1/4] Taking Baseline Snapshot...")
    baseline_report = run_validator(target_dir, mode)
    baseline_sigs = extract_signatures(baseline_report)

    # 2. Apply Patch
    print("\n🛠️ [2/4] Applying Patch...")
    if not apply_patch(target_dir, patch_file):
        sys.exit(1)

    # 3. Snapshot Post-Patch
    print("\n📸 [3/4] Taking Post-Patch Snapshot...")
    post_report = run_validator(target_dir, mode)
    post_sigs = extract_signatures(post_report)

    # 4. Delta Analysis
    print("\n📊 [4/4] Delta Analysis...")
    approved = True
    rollback_reason = []

    for file, post_sig in post_sigs.items():
        base_sig = baseline_sigs.get(file)
        if not base_sig:
            if not post_sig["passed"] or post_sig["security_flags"] > 0:
                approved = False
                rollback_reason.append({
                    "file": file,
                    "reason": "new_file_failed_validation",
                    "details": {"security_flags": post_sig["security_flags"], "passed": post_sig["passed"]}
                })
            continue
        
        # Delta Math
        score_delta = post_sig["validation_score"] - base_sig["validation_score"]
        security_delta = post_sig["security_flags"] - base_sig["security_flags"]
        complexity_delta = post_sig["complexity"] - base_sig["complexity"]
        risk_delta = post_sig["risk_score"] - base_sig["risk_score"]

        # 5. Neutral changes allowed
        if score_delta == 0 and security_delta == 0 and risk_delta == 0:
            continue # perfectly neutral, allow it.

        if security_delta > 0:
            approved = False
            rollback_reason.append({
                "file": file,
                "reason": "security_flags_increased",
                "details": {"before": base_sig["security_flags"], "after": post_sig["security_flags"]}
            })

        # 1. Validation score tolerance (allow up to -3 point drop for dead code removal etc)
        if score_delta < -3:
            approved = False
            rollback_reason.append({
                "file": file,
                "reason": "validation_score_degraded",
                "details": {"before": base_sig["validation_score"], "after": post_sig["validation_score"], "delta": score_delta}
            })

    # 3. Confidence vs Outcome Logging (Append to forge_outcomes.json)
    outcome_log = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "patch_target": target_dir,
        "actual_outcome": "approved" if approved else "rejected",
        "reasons": rollback_reason
    }
    with open(os.path.join(target_dir, "forge_outcomes.json"), "a") as f:
        f.write(json.dumps(outcome_log) + "\n")

    # 4. Structured JSON Output
    if "FORGE_JSON_OUTPUT" in os.environ:
        result_payload = {
            "status": "approved" if approved else "rejected",
            "reasons": rollback_reason
        }
        print(json.dumps(result_payload))
        sys.exit(0 if approved else 1)

    print("\n" + "="*50)
    if approved:
        print("✅ PATCH APPROVED. Delta passed all gates.")
        sys.exit(0)
    else:
        print("❌ PATCH REJECTED. Rolling back...")
        print(json.dumps({"status": "rejected", "reasons": rollback_reason}, indent=2))
        rollback_patch(target_dir, patch_file)
        sys.exit(1)

if __name__ == "__main__":
    main()
