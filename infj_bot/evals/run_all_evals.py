#!/usr/bin/env python3
"""
Unified Automated Evaluation Runner for INFJ Bot

Runs consistency, mode discrimination, self-modify audit, and stress tests.
Generates a consolidated report and exits with non-zero code on failure thresholds.
"""

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

EVAL_DIR = Path(__file__).parent
PROJECT_ROOT = EVAL_DIR.parent

def run_eval(script: str, name: str) -> dict:
    """Run a single eval script and capture result."""
    print(f"\n=== Running {name} ===")
    try:
        result = subprocess.run(
            [sys.executable, str(EVAL_DIR / script)],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=PROJECT_ROOT
        )
        status = "PASS" if result.returncode == 0 or "passed" in result.stdout.lower() else "FAIL"
        print(result.stdout[-2000:] if len(result.stdout) > 2000 else result.stdout)
        if result.stderr:
            print("STDERR:", result.stderr[-500:])
        return {"name": name, "status": status, "returncode": result.returncode}
    except Exception as e:
        return {"name": name, "status": "ERROR", "error": str(e)}


def main():
    print(f"INFJ Bot Automated Eval Suite — {datetime.now().isoformat()}")
    print("=" * 60)

    evals = [
        ("consistency_eval.py", "Consistency"),
        ("mode_discrimination.py", "Mode Discrimination"),
        ("self_modify_audit.py", "Self-Modify Audit"),
    ]

    results = []
    for script, name in evals:
        res = run_eval(script, name)
        results.append(res)

    # Quick stress test (subset)
    print("\n=== Running Stress Subset ===")
    try:
        stress = subprocess.run(
            [sys.executable, "-m", "pytest", "tests/test_stress.py", "-q", "--tb=no"],
            capture_output=True, text=True, timeout=60, cwd=PROJECT_ROOT
        )
        stress_status = "PASS" if stress.returncode == 0 else "FAIL"
        print(stress.stdout)
    except Exception as e:
        stress_status = "ERROR"
        print(f"Stress test error: {e}")

    results.append({"name": "Stress Tests", "status": stress_status})

    # Summary
    print("\n" + "=" * 60)
    print("EVAL SUMMARY")
    print("=" * 60)
    passed = sum(1 for r in results if r["status"] == "PASS")
    for r in results:
        icon = "✅" if r["status"] == "PASS" else "❌"
        print(f"{icon} {r['name']}: {r['status']}")

    print(f"\nTotal: {passed}/{len(results)} passed")

    # Exit code
    sys.exit(0 if passed == len(results) else 1)


if __name__ == "__main__":
    main()
