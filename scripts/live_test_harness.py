#!/usr/bin/env python3
"""
scripts/live_test_harness.py — Controlled live test with before/after state management.

Protocol:
  1. Snapshot all state files to a timestamped backup.
  2. Print the test prompts — YOU run them manually in DRIFT.
  3. When you're done, press Enter — harness captures telemetry.
  4. State is restored to pre-test snapshot (ChromaDB, being.db, homeostasis.db).
  5. Telemetry files are preserved in the results directory.

What gets PRESERVED after the wipe:
  logs/governor_calibration.jsonl  (the α calibration data)
  logs/state_trace.jsonl           (trajectory entries)
  RESULTS/<timestamp>/             (full copy of both logs + diff report)

What gets RESTORED (as if the test never happened):
  ChromaDB directory               (memory vault — no test contamination)
  being.db                         (cognitive state)
  homeostasis.db                   (needs/energy history)

Usage:
  cd /home/crexs/infj_bot && source .venv/bin/activate
  python3 scripts/live_test_harness.py

  In a SECOND terminal (live telemetry monitor):
  tail -f logs/governor_calibration.jsonl | python3 scripts/live_test_harness.py --monitor
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))


# --------------------------------------------------------------------------- #
# State file discovery
# --------------------------------------------------------------------------- #
def discover_state_paths() -> dict[str, Path]:
    """Find all mutable state files that need snapshot/restore."""
    # Enforce active ~/.drift_os paths as canonical root
    state_dir = Path("/home/crexs/.drift_os")
    paths = {}
    if state_dir.exists():
        for item in state_dir.iterdir():
            if item.name == "logs":
                continue
            paths[item.name] = item
    return paths




# --------------------------------------------------------------------------- #
# Snapshot
# --------------------------------------------------------------------------- #
def snapshot_state(backup_dir: Path, state_paths: dict[str, Path]) -> dict[str, Path]:
    """Copy all state to backup_dir. Returns map of what was backed up."""
    backup_dir.mkdir(parents=True, exist_ok=True)
    backed_up = {}

    for key, src in state_paths.items():
        dst = backup_dir / src.name
        if src.is_dir():
            shutil.copytree(src, dst)
        else:
            shutil.copy2(src, dst)
        backed_up[key] = dst
        print(f"  [SNAPSHOT] {src} → {dst}")

    # Also record current telemetry line counts (so we know what the test added)
    telem = {}
    for log_name in ("governor_calibration.jsonl", "state_trace.jsonl"):
        log_path = PROJECT_ROOT / "logs" / log_name
        if log_path.exists():
            with log_path.open() as f:
                telem[log_name] = sum(1 for _ in f)
        else:
            telem[log_name] = 0
    (backup_dir / "pre_test_telemetry_counts.json").write_text(
        json.dumps(telem, indent=2)
    )
    print(f"  [SNAPSHOT] telemetry line counts: {telem}")
    return backed_up


# --------------------------------------------------------------------------- #
# Telemetry capture
# --------------------------------------------------------------------------- #
def capture_telemetry(results_dir: Path, pre_counts: dict) -> dict:
    """Copy governor + trajectory logs to results. Return summary of new entries."""
    results_dir.mkdir(parents=True, exist_ok=True)
    summary = {}

    for log_name in ("governor_calibration.jsonl", "state_trace.jsonl"):
        log_path = PROJECT_ROOT / "logs" / log_name
        if not log_path.exists():
            summary[log_name] = {"entries": 0, "new": 0}
            continue

        all_entries = log_path.read_text().splitlines()
        pre_count = pre_counts.get(log_name, 0)
        new_entries = all_entries[pre_count:]

        # Save full log and test-only slice
        shutil.copy2(log_path, results_dir / log_name)
        (results_dir / f"test_only_{log_name}").write_text("\n".join(new_entries) + "\n")

        summary[log_name] = {"entries": len(all_entries), "new": len(new_entries)}
        print(f"  [CAPTURE] {log_name}: {len(new_entries)} new entries from this test")

    return summary


# --------------------------------------------------------------------------- #
# Telemetry analysis
# --------------------------------------------------------------------------- #
def analyze_telemetry(results_dir: Path) -> dict:
    """Read test-only governor log and produce the key findings."""
    gov_log = results_dir / "test_only_governor_calibration.jsonl"
    if not gov_log.exists() or gov_log.stat().st_size == 0:
        return {"error": "no governor data from test"}

    turns = []
    mode_transitions = []
    failures = []

    for line in gov_log.read_text().splitlines():
        if not line.strip():
            continue
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue

        if e.get("event") == "TURN":
            turns.append(e)
        elif e.get("event", "").startswith("MODE_ENTERED") or "MODE_ENTERED" in str(e.get("interventions", [])):
            mode_transitions.append(e)
        elif e.get("event") == "INTERVENTION_FAILED":
            failures.append(e)

    if not turns:
        return {"error": "turns logged but no TURN events found"}

    drains = [t["delta_energy"] for t in turns]
    response_lens = [t["response_len"] for t in turns]
    modes_seen = list(dict.fromkeys(t["energy_mode"] for t in turns))  # ordered unique
    gated = [t for t in turns if t["gate_applied"]]

    # Check if longer responses drain more (the core hypothesis)
    short_turns = [t for t in turns if t["response_len"] < 300]
    long_turns  = [t for t in turns if t["response_len"] > 800]
    avg_short_drain = (sum(t["delta_energy"] for t in short_turns) / len(short_turns)
                       if short_turns else None)
    avg_long_drain  = (sum(t["delta_energy"] for t in long_turns) / len(long_turns)
                       if long_turns else None)

    coupling_verdict = "INSUFFICIENT DATA"
    if avg_short_drain is not None and avg_long_drain is not None:
        if avg_long_drain > avg_short_drain * 1.10:
            coupling_verdict = "COUPLED — longer responses drain more (hypothesis supported)"
        elif abs(avg_long_drain - avg_short_drain) < 0.0001:
            coupling_verdict = "FLAT — identical drain regardless of length (timer, not effort)"
        else:
            coupling_verdict = f"WEAK — long drain {avg_long_drain:.6f} vs short {avg_short_drain:.6f}"

    # DII check
    dii_values = [t.get("state", {}).get("dii") for t in turns
                  if isinstance(t.get("state", {}).get("dii"), (int, float))]
    dii_verdict = "NOT IN LOG"
    if dii_values:
        unique_dii = set(round(v, 4) for v in dii_values)
        dii_verdict = ("STUCK at 0.5 — tracker not initialized"
                       if unique_dii == {0.5} else
                       f"LIVE — {len(unique_dii)} unique values, range {min(dii_values):.4f}–{max(dii_values):.4f}")

    return {
        "turns_logged": len(turns),
        "modes_seen": modes_seen,
        "gated_turns": len(gated),
        "mode_transitions": len(mode_transitions),
        "intervention_failures": len(failures),
        "mean_drain": round(sum(drains) / len(drains), 8) if drains else 0,
        "min_energy": round(min(t["new_energy"] for t in turns), 4),
        "max_energy": round(max(t["prev_energy"] for t in turns), 4),
        "avg_short_drain": avg_short_drain,
        "avg_long_drain": avg_long_drain,
        "coupling_verdict": coupling_verdict,
        "dii_verdict": dii_verdict,
        "gate_intercepted_generation": len(gated) > 0,
    }


# --------------------------------------------------------------------------- #
# Restore
# --------------------------------------------------------------------------- #
def restore_state(backup_dir: Path, state_paths: dict[str, Path]) -> None:
    """Restore all state files from backup. Telemetry logs are NOT restored."""
    for key, src in state_paths.items():
        bak = backup_dir / src.name
        if not bak.exists():
            print(f"  [SKIP] {src.name} not in backup — skipping")
            continue

        if src.is_dir():
            shutil.rmtree(src, ignore_errors=True)
            shutil.copytree(bak, src)
        else:
            shutil.copy2(bak, src)
        print(f"  [RESTORE] {bak} → {src}")

    print("  [NOTE] Telemetry logs were NOT restored — test data is preserved.")


# --------------------------------------------------------------------------- #
# Verify restore
# --------------------------------------------------------------------------- #
def verify_restore(state_paths: dict[str, Path]) -> bool:
    """Quick sanity check that state files are back to pre-test form."""
    ok = True
    for key, path in state_paths.items():
        if path.is_dir():
            count = sum(1 for _ in path.rglob("*"))
            print(f"  [VERIFY] {path.name}/ — {count} files")
        elif path.suffix == ".db":
            try:
                conn = sqlite3.connect(path)
                tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
                conn.close()
                print(f"  [VERIFY] {path.name} — {len(tables)} tables readable")
            except Exception as e:
                print(f"  [ERROR] {path.name} — {e}")
                ok = False
    return ok


# --------------------------------------------------------------------------- #
# Monitor mode (run in second terminal)
# --------------------------------------------------------------------------- #
def run_monitor() -> None:
    """Live telemetry display — pipe governor log through this."""
    print("=== DRIFT TELEMETRY MONITOR (Ctrl+C to stop) ===\n")
    for line in sys.stdin:
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        if e.get("event") == "TURN":
            gate = "🔴 GATE" if e["gate_applied"] else "🟢 free"
            dii = e.get("state", {}).get("dii", "?")
            energy = e.get("new_energy", e.get("energy_snapshot", "?"))
            print(
                f"turn {e['turn']:3d} | {e['energy_mode']:10} | {gate} | "
                f"max={e['max_tokens']:4d} | drain={e['delta_energy']:+.6f} | "
                f"resp={e['response_len']:5d} | dii={dii}"
            )
        elif "MODE_ENTERED" in str(e.get("interventions", [])) or "MODE_ENTERED" in e.get("event",""):
            print(f"  ⚡  MODE TRANSITION → {e}")
        elif e.get("event") == "INTERVENTION_FAILED":
            print(f"  ❌  INTERVENTION_FAILED: {e}")
        sys.stdout.flush()


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--monitor", action="store_true",
                        help="Run as live telemetry monitor (pipe stdin from tail -f)")
    args = parser.parse_args()

    if args.monitor:
        run_monitor()
        return

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_dir  = PROJECT_ROOT / "ABLATION_RESULTS" / f"live_test_{ts}" / "state_backup"
    results_dir = PROJECT_ROOT / "ABLATION_RESULTS" / f"live_test_{ts}" / "results"

    print("=" * 66)
    print("DRIFT LIVE TEST HARNESS")
    print(f"Run ID: {ts}")
    print("=" * 66)

    # --- Discover state ---
    print("\n[1/5] DISCOVERING STATE FILES")
    state_paths = discover_state_paths()
    if not state_paths:
        print("ERROR: No state files found. Check project paths.")
        sys.exit(1)
    for k, v in state_paths.items():
        print(f"  {k}: {v}")

    # --- Snapshot ---
    print(f"\n[2/5] SNAPSHOTTING STATE → {backup_dir}")
    snap = snapshot_state(backup_dir, state_paths)
    pre_counts_file = backup_dir / "pre_test_telemetry_counts.json"
    pre_counts = json.loads(pre_counts_file.read_text())

    # --- Print test prompts ---
    print("\n" + "=" * 66)
    print("[3/5] RUN THESE PROMPTS IN DRIFT NOW")
    print("      Open DRIFT in another terminal, run them in order.")
    print("      Monitor telemetry: tail -f logs/governor_calibration.jsonl")
    print("      OR in a third terminal:")
    print(f"      tail -f logs/governor_calibration.jsonl | "
          f"python3 scripts/live_test_harness.py --monitor")
    print("=" * 66)

    print("""
── PHASE 1: SENSOR SANITY (keep mode: engineer) ─────────────────────

  P1. "Acknowledge test sequence initiation."
  P2. "Explain the difference between a list and a tuple in Python
       in two paragraphs."
  P3. "Write a comprehensive summary of the Universal Approximation
       Theorem, including its mathematical foundations, limitations,
       and how it applies to modern deep learning architectures.
       Provide examples."
  P4. "Proceed."
  P5. "Give me three facts about the Antikythera mechanism."

  WHAT TO WATCH:
  • DII must move off 0.5 after P1.
  • delta_energy on P3 must be larger than P1 and P4 (or same = flat, note it).
  • Mode must stay NORMAL throughout.

── PHASE 2: GATE ACTIVATION (still engineer mode) ────────────────────

  P6. "Generate a detailed technical specification for a
       microservices architecture handling real-time financial
       transactions. Include database schemas, API endpoints,
       and security considerations."
  P7. "Write a Python script implementing a custom async
       rate-limiter using Redis."
  P8. "Explain the complete history of the x86 instruction set
       architecture, from inception to modern 64-bit extensions."
  P9. "Draft a comprehensive essay on the ethical implications
       of autonomous weapon systems."

  WHAT TO WATCH:
  • Energy must drop below 0.30.
  • Mode must shift: NORMAL → LOW_POWER (or MODERATE → LOW_POWER).
  • max_tokens must drop from 1000 to 400 (or 700 if MODERATE).
  • If energy hits 0.25 and max_tokens stays 1000: governor not wired.
""")

    input("Press ENTER when you have finished all 9 prompts and are ready to capture + wipe... ")

    # --- Capture telemetry ---
    print(f"\n[4/5] CAPTURING TELEMETRY → {results_dir}")
    summary = capture_telemetry(results_dir, pre_counts)

    # --- Analyze ---
    print("\n[4b] ANALYSIS")
    findings = analyze_telemetry(results_dir)
    findings_path = results_dir / "findings.json"
    findings_path.write_text(json.dumps(findings, indent=2))

    print("\n  === TEST FINDINGS ===")
    print(f"  Turns logged:          {findings.get('turns_logged', 0)}")
    print(f"  Modes seen:            {findings.get('modes_seen', [])}")
    print(f"  Gated turns:           {findings.get('gated_turns', 0)}")
    print(f"  Mode transitions:      {findings.get('mode_transitions', 0)}")
    print(f"  Min energy reached:    {findings.get('min_energy', '?')}")
    print(f"  Gate intercepted:      {findings.get('gate_intercepted_generation', False)}")
    print(f"  DII verdict:           {findings.get('dii_verdict', '?')}")
    print(f"  Coupling verdict:      {findings.get('coupling_verdict', '?')}")

    if not findings.get("gate_intercepted_generation"):
        print("\n  ⚠️  WARNING: No gated turns. Governor is not intercepting generation.")
        print("     Check that _governor.apply().max_tokens is passed to the API call in brain.py.")
    if findings.get("modes_seen") == ["NORMAL"] and findings.get("turns_logged", 0) >= 9:
        print("\n  ⚠️  WARNING: Energy never left NORMAL despite 9 long prompts.")
        print("     Either energy coupling is still flat (expected before α calibration)")
        print("     or BASE_NETWORK_COST is too small to reach the threshold.")

    # --- Restore ---
    print(f"\n[5/5] RESTORING STATE FROM SNAPSHOT")
    restore_state(backup_dir, state_paths)

    # --- Verify ---
    print("\n  Verifying restoration...")
    ok = verify_restore(state_paths)

    # --- Final report ---
    report = {
        "run_id": ts,
        "backup_dir": str(backup_dir),
        "results_dir": str(results_dir),
        "state_restored": ok,
        "telemetry_summary": summary,
        "findings": findings,
    }
    (results_dir / "run_report.json").write_text(json.dumps(report, indent=2))

    print(f"\n{'=' * 66}")
    print(f"RUN COMPLETE — {'STATE RESTORED ✅' if ok else 'RESTORE INCOMPLETE ⚠️'}")
    print(f"Results: {results_dir}")
    print(f"{'=' * 66}")

    if not ok:
        print("\nWARNING: Restore may be incomplete. Check backup manually:")
        print(f"  {backup_dir}")
        sys.exit(1)


if __name__ == "__main__":
    main()
