#!/usr/bin/env python3
"""Quick analysis tool for security_audit.jsonl"""

import json
from pathlib import Path
from collections import Counter
import statistics


def analyze_security_audit(log_path: str = "security_audit.jsonl", last_n: int = 500):
    path = Path(log_path)
    if not path.exists():
        print(f"❌ Log file not found: {path}")
        return

    logs = []
    with open(path, "r", encoding="utf-8") as f:
        for line in list(f)[-last_n:]:
            try:
                logs.append(json.loads(line.strip()))
            except:
                continue

    if not logs:
        print("No logs found.")
        return

    print(f"\n=== PHI/DRIFT Security Audit Analysis (last {len(logs)} entries) ===\n")

    # Basic stats
    actions = Counter(log.get("action", "unknown") for log in logs)
    categories = Counter(log.get("category", "unknown") for log in logs)
    high_risk = [log for log in logs if log.get("social_risk", 0) > 0.5]
    blocked = [log for log in logs if log.get("action") == "block"]

    print("Actions:")
    for action, count in actions.most_common():
        print(f"  {action:10} : {count}")

    print("\nThreat Categories:")
    for cat, count in categories.most_common(8):
        print(f"  {cat:20} : {count}")

    print(
        f"\nHigh Social Risk Events: {len(high_risk)} ({len(high_risk) / len(logs) * 100:.1f}%)"
    )
    print(f"Blocked Events: {len(blocked)} ({len(blocked) / len(logs) * 100:.1f}%)")

    # PEDI / DII correlation
    pedi_values = [log.get("pedi_value", 0) for log in logs if log.get("pedi_value")]
    dii_values = [log.get("dii_value", 0) for log in logs if log.get("dii_value")]

    if pedi_values:
        print(
            f"\nPEDI  — mean: {statistics.mean(pedi_values):.3f}  min: {min(pedi_values):.3f}  max: {max(pedi_values):.3f}"
        )
    if dii_values:
        print(
            f"DII   — mean: {statistics.mean(dii_values):.3f}  min: {min(dii_values):.3f}  max: {max(dii_values):.3f}"
        )

    # Recent high-risk summary
    if high_risk:
        print("\n--- Recent High-Risk Events ---")
        for log in high_risk[-5:]:
            print(
                f"  {log['ts'][:19]} | {log.get('action', '?'):6} | social={log.get('social_risk', 0):.2f} | PEDI={log.get('pedi_value', 0):.2f}"
            )


if __name__ == "__main__":
    analyze_security_audit()
