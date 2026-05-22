"""
inspect_logs.py
DRIFT Log Inspector
--------------------
Use this after the first baseline session to manually verify the database
contains all expected fields before running ablations.

DO NOT skip this step. If fields are missing here, your ablation data
will be incomplete and you will not know until analysis.

Usage:
    python inspect_logs.py                    # inspect all runs
    python inspect_logs.py --run_id run_xyz   # inspect specific run
    python inspect_logs.py --summary          # summary stats only
"""

import sqlite3
import json
import argparse
from pathlib import Path


DB_PATH = "experiment_log.db"

REQUIRED_EVENT_TYPES = [
    "state_snapshot",
    "memory_selection",
    "continuity_metrics",
]

REQUIRED_RUN_FIELDS = [
    "run_id",
    "config",
    "git_hash",
    "start_time",
]


def connect():
    if not Path(DB_PATH).exists():
        print(f"[Inspector] Database not found: {DB_PATH}")
        print("Run collect_baseline.py first.")
        return None
    return sqlite3.connect(DB_PATH)


def list_runs(conn):
    cur = conn.execute("SELECT run_id, git_hash, start_time, config FROM runs ORDER BY start_time DESC")
    rows = cur.fetchall()
    print(f"\n[Runs] Found {len(rows)} runs:\n")
    for run_id, git_hash, start_time, config_str in rows:
        config = json.loads(config_str)
        mode = config.get("mode", "?")
        print(f"  {run_id}")
        print(f"    mode:     {mode}")
        print(f"    git_hash: {git_hash}")
        print(f"    started:  {start_time}")
        print()
    return [r[0] for r in rows]


def inspect_run(conn, run_id: str):
    print(f"\n[Inspecting] Run: {run_id}")

    # Check run record
    cur = conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,))
    run = cur.fetchone()
    if not run:
        print(f"  ❌ Run not found in runs table.")
        return

    print(f"  ✅ Run record found.")

    # Check git hash
    git_hash = run[2]  # column index
    if git_hash == "unknown":
        print(f"  ⚠️  git_hash = 'unknown'. Not in a git repo or git not available.")
    else:
        print(f"  ✅ git_hash: {git_hash}")

    # Check event types present
    cur = conn.execute(
        "SELECT DISTINCT event_type FROM events WHERE run_id = ?", (run_id,)
    )
    found_types = {row[0] for row in cur.fetchall()}
    print(f"\n  [Event Types Found]")
    for et in REQUIRED_EVENT_TYPES:
        status = "✅" if et in found_types else "❌ MISSING"
        print(f"    {status}  {et}")
    for et in found_types - set(REQUIRED_EVENT_TYPES):
        print(f"    ➕  {et}")

    # Check run_end exists
    cur = conn.execute(
        "SELECT COUNT(*) FROM events WHERE run_id = ? AND event_type = 'run_end'",
        (run_id,)
    )
    has_end = cur.fetchone()[0] > 0
    print(f"\n  [Run End] {'✅ Clean run_end logged' if has_end else '❌ No run_end found — run may have crashed'}")

    # Sample a memory_selection event
    cur = conn.execute(
        "SELECT payload FROM events WHERE run_id = ? AND event_type = 'memory_selection' LIMIT 1",
        (run_id,)
    )
    row = cur.fetchone()
    if row:
        payload = json.loads(row[0])
        print(f"\n  [Sample memory_selection]")
        selected = payload.get("selected", [])
        rejected = payload.get("rejected", [])
        print(f"    selected:  {len(selected)} memories")
        print(f"    rejected:  {len(rejected)} candidates")
        if selected:
            s = selected[0]
            components = s.get("components")
            if components:
                print(f"    ✅ score_components present: {list(components.keys())}")
            else:
                print(f"    ❌ score_components MISSING from selected[0]")
    else:
        print(f"\n  ⚠️  No memory_selection events found.")

    # Sample a continuity_metrics event
    cur = conn.execute(
        "SELECT payload FROM events WHERE run_id = ? AND event_type = 'continuity_metrics' LIMIT 1",
        (run_id,)
    )
    row = cur.fetchone()
    if row:
        payload = json.loads(row[0])
        print(f"\n  [Sample continuity_metrics]")
        normalized = payload.get("normalized", {})
        raw = payload.get("raw", {})
        axes = ["entity_overlap", "goal_overlap", "tone_similarity", "memory_reference_rate", "state_influence"]
        for axis in axes:
            n_val = normalized.get(axis, "MISSING")
            r_val = raw.get(axis, "MISSING")
            status = "✅" if n_val != "MISSING" else "❌"
            print(f"    {status}  {axis}: raw={r_val}, normalized={n_val}")
    else:
        print(f"\n  ⚠️  No continuity_metrics events found.")

    # Event count
    cur = conn.execute(
        "SELECT COUNT(*) FROM events WHERE run_id = ?", (run_id,)
    )
    count = cur.fetchone()[0]
    print(f"\n  [Total Events] {count}")


def summary(conn):
    cur = conn.execute("SELECT COUNT(*) FROM runs")
    n_runs = cur.fetchone()[0]
    cur = conn.execute("SELECT COUNT(*) FROM events")
    n_events = cur.fetchone()[0]
    cur = conn.execute("SELECT COUNT(DISTINCT run_id) FROM events WHERE event_type = 'run_end'")
    n_clean = cur.fetchone()[0]

    print(f"\n[Summary]")
    print(f"  Total runs:        {n_runs}")
    print(f"  Total events:      {n_events}")
    print(f"  Clean completions: {n_clean}")
    print(f"  Incomplete runs:   {n_runs - n_clean}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="DRIFT Log Inspector")
    parser.add_argument("--run_id", type=str, default=None)
    parser.add_argument("--summary", action="store_true")
    args = parser.parse_args()

    conn = connect()
    if conn is None:
        exit(1)

    if args.summary:
        summary(conn)
    elif args.run_id:
        inspect_run(conn, args.run_id)
    else:
        run_ids = list_runs(conn)
        if run_ids:
            print("[Inspector] Inspecting most recent run...")
            inspect_run(conn, run_ids[0])
        summary(conn)

    conn.close()
