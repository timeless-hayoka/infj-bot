"""
psc_live_telemetry.py — Real being.db Validation
==================================================
Loads actual cognitive state history from being.db and homeostasis.db,
runs PSC Scaled V4 engine against it, and outputs:

  1. Alert timeline — when PSC would have fired and at what intensity
  2. Chaos score distribution over real sessions (vs synthetic assumptions)
  3. Dimension coverage — which dims have enough history to project
  4. PEDI precursor stats — behavioral continuity signals (without defining
     final thresholds — those require 2+ weeks of sessions)
  5. Policy mode recommendation based on observed volatility profile

This script READS ONLY. No writes to being.db or homeostasis.db.

Usage:
  python psc_live_telemetry.py
  python psc_live_telemetry.py --db path/to/being.db --limit 500
  python psc_live_telemetry.py --policy SECURITY --export results.json

DRIFT V4 | Julien James (CREX)
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import time
import warnings
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

import numpy as np

warnings.filterwarnings("ignore")

# ── Path resolution ────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

try:
    from psc_scaled import PSCBatchEngine, DIMENSION_POLARITY, POLICY_CONFIG
    PSC_AVAILABLE = True
except ImportError:
    PSC_AVAILABLE = False
    print("[WARN] psc_scaled.py not found in path. Using fallback dimension list.")
    DIMENSION_POLARITY = {
        "focus": 1, "coherence": 1, "stability": 1, "clarity": 1,
        "energy": 1, "alignment": 1, "confidence": 1, "resilience": 1,
        "situational_awareness": 1, "task_progress": 1,
        "context_integrity": 1, "memory_coherence": 1,
        "threat_pressure": -1, "error_pressure": -1,
        "latency_pressure": -1, "resource_pressure": -1,
    }


# ── Config ─────────────────────────────────────────────────────────────────────
DEFAULT_BEING_DB       = os.environ.get("DRIFT_BEING_DB", "being.db")
DEFAULT_HOMEOSTASIS_DB = os.environ.get("DRIFT_HOMEOSTASIS_DB", "homeostasis.db")
DEFAULT_POLICY         = "BALANCED"
DEFAULT_LIMIT          = 1000   # max rows to load


# ── Data loading ───────────────────────────────────────────────────────────────

def _discover_tables(conn: sqlite3.Connection) -> list[str]:
    cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    return [r[0] for r in cur.fetchall()]


def _discover_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    cur = conn.execute(f"PRAGMA table_info({table})")
    return [r[1] for r in cur.fetchall()]


def load_being_db(db_path: str, limit: int = DEFAULT_LIMIT) -> list[dict]:
    """
    Load cognitive state rows from being.db.
    Handles schema variations — reads whatever numeric columns exist.
    Returns rows oldest-first as list of dicts.
    """
    if not os.path.exists(db_path):
        print(f"[ERROR] being.db not found: {db_path}")
        print(f"  Set DRIFT_BEING_DB env var or pass --db")
        return []

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    tables = _discover_tables(conn)
    print(f"[DB] Tables in {db_path}: {tables}")

    # Try common table names
    target_table = None
    for candidate in ["cognitive_state", "being_state", "state", "states",
                       "cognitive_states", "drift_state"]:
        if candidate in tables:
            target_table = candidate
            break

    if not target_table and tables:
        target_table = tables[0]
        print(f"[DB] No known table name found, trying: {target_table}")

    if not target_table:
        print("[ERROR] being.db has no tables. Has DRIFT run any sessions yet?")
        conn.close()
        return []

    cols = _discover_columns(conn, target_table)
    print(f"[DB] Columns in {target_table}: {cols}")

    # Load
    try:
        order_col = "timestamp" if "timestamp" in cols else (
            "id" if "id" in cols else cols[0]
        )
        cur = conn.execute(
            f"SELECT * FROM {target_table} ORDER BY {order_col} ASC LIMIT ?",
            (limit,)
        )
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        print(f"[DB] Loaded {len(rows)} rows from {target_table}")
        return rows
    except Exception as e:
        print(f"[ERROR] Query failed: {e}")
        conn.close()
        return []


def normalize_row(row: dict, target_dims: list[str]) -> dict:
    """
    Normalize a raw DB row to the PSC dimension space.
    Maps any numeric column to the closest matching dimension name.
    Unknown columns are ignored; missing target dims get None.
    """
    normalized = {}
    row_lower = {k.lower(): v for k, v in row.items()}

    for dim in target_dims:
        # Direct match
        if dim in row:
            val = row[dim]
        elif dim.lower() in row_lower:
            val = row_lower[dim.lower()]
        else:
            # Try partial match (e.g., "focus_score" → "focus")
            val = next(
                (v for k, v in row_lower.items()
                 if dim in k and isinstance(v, (int, float))),
                None
            )
        if isinstance(val, (int, float)) and not np.isnan(float(val)):
            normalized[dim] = float(np.clip(val, 0.0, 1.0))

    return normalized


# ── Analysis ───────────────────────────────────────────────────────────────────

@dataclass
class TelemetryReport:
    total_rows:          int
    covered_dims:        list[str]     # dims with enough data to project
    sparse_dims:         list[str]     # dims present but < MIN_HISTORY
    missing_dims:        list[str]     # dims not found in DB at all
    alert_count:         int
    alert_timeline:      list[dict]    # {cycle, dim, intensity, chaos, confidence}
    chaos_distribution:  dict          # per-dim: {mean, std, min, max}
    policy_used:         str
    sessions_estimated:  int           # rough estimate based on row count
    pedi_precursors:     dict          # pre-metric signals for PEDI framework
    recommendation:      str


def run_telemetry_validation(
    rows: list[dict],
    policy: str = DEFAULT_POLICY,
    dims: Optional[list[str]] = None,
) -> TelemetryReport:
    """
    Core validation loop. Feeds real DB rows through PSC engine cycle by cycle.
    """
    if not PSC_AVAILABLE:
        print("[ERROR] psc_scaled module not available. Cannot run engine.")
        sys.exit(1)

    target_dims = dims or list(DIMENSION_POLARITY.keys())
    engine = PSCBatchEngine(target_dims, policy=policy)

    alert_timeline   = []
    chaos_per_dim    = {d: [] for d in target_dims}
    conf_per_dim     = {d: [] for d in target_dims}
    alert_count      = 0
    covered_dims     = set()
    present_dims     = set()

    print(f"\n[PSC] Running against {len(rows)} real telemetry rows (policy={policy})...")
    t_start = time.perf_counter()

    for cycle, row in enumerate(rows):
        state = normalize_row(row, target_dims)

        if not state:
            continue

        present_dims.update(state.keys())
        engine.push_state(state)
        result = engine.run()

        if result is None:
            continue

        # Track chaos scores per dim
        for i, dim in enumerate(target_dims):
            if dim in state:
                covered_dims.add(dim)
                chaos_per_dim[dim].append(float(result.chaos_scores[i]))
                conf_per_dim[dim].append(float(result.confidence[i]))

        # Record alerts
        if result.alerted.any():
            for i, dim in enumerate(target_dims):
                if result.alerted[i]:
                    alert_count += 1
                    alert_timeline.append({
                        "cycle":      cycle,
                        "row_id":     row.get("id", cycle),
                        "timestamp":  str(row.get("timestamp", "")),
                        "dimension":  dim,
                        "current":    float(result.current[i]),
                        "predicted":  float(result.predicted[i]),
                        "chaos":      float(result.chaos_scores[i]),
                        "confidence": float(result.confidence[i]),
                        "n_steps":    int(result.n_steps_used[i]),
                        "intensity":  (
                            "hard"   if result.confidence[i] >= 0.75 else
                            "medium" if result.confidence[i] >= 0.55 else
                            "soft"
                        ),
                    })

    elapsed = time.perf_counter() - t_start
    print(f"[PSC] Completed in {elapsed:.2f}s ({len(rows)/elapsed:.0f} rows/sec)")

    # Dimension coverage analysis
    sparse_dims  = [d for d in target_dims if d in present_dims and d not in covered_dims]
    missing_dims = [d for d in target_dims if d not in present_dims]

    # Chaos distribution per covered dimension
    chaos_dist = {}
    for dim in covered_dims:
        vals = np.array(chaos_per_dim[dim])
        if len(vals) > 0:
            chaos_dist[dim] = {
                "mean":  float(vals.mean()),
                "std":   float(vals.std()),
                "min":   float(vals.min()),
                "max":   float(vals.max()),
                "p95":   float(np.percentile(vals, 95)),
            }

    # PEDI precursor signals
    # These are raw behavioral continuity signals — NOT final PEDI thresholds
    # Thresholds require 2+ weeks of session data to derive empirically
    pedi_precursors = {
        "alert_rate_per_100_cycles": (alert_count / max(len(rows), 1)) * 100,
        "mean_chaos_across_dims":    float(np.mean([
            v["mean"] for v in chaos_dist.values()
        ])) if chaos_dist else 0.0,
        "dim_coverage_fraction":     len(covered_dims) / len(target_dims),
        "high_chaos_dim_count":      sum(
            1 for v in chaos_dist.values() if v["mean"] > 0.50
        ),
        "total_hard_alerts":         sum(
            1 for a in alert_timeline if a["intensity"] == "hard"
        ),
        "total_soft_alerts":         sum(
            1 for a in alert_timeline if a["intensity"] == "soft"
        ),
        "note": (
            "These are raw signals only. Do not derive PEDI thresholds until "
            "2+ weeks of real session data is accumulated."
        ),
    }

    # Policy recommendation based on observed chaos profile
    mean_chaos = pedi_precursors["mean_chaos_across_dims"]
    if mean_chaos > 0.55:
        rec = "SECURITY — observed high ambient chaos. Tighten confidence gate."
    elif mean_chaos < 0.25:
        rec = "CONSERVATIVE — system is stable. Can afford stricter confidence threshold."
    else:
        rec = "BALANCED — observed chaos profile matches expected production range."

    # Rough session estimate (assume ~60-120 rows per session)
    sessions_estimated = max(1, len(rows) // 90)

    return TelemetryReport(
        total_rows        = len(rows),
        covered_dims      = sorted(covered_dims),
        sparse_dims       = sorted(sparse_dims),
        missing_dims      = sorted(missing_dims),
        alert_count       = alert_count,
        alert_timeline    = alert_timeline[:100],   # cap for readability
        chaos_distribution= chaos_dist,
        policy_used       = policy,
        sessions_estimated= sessions_estimated,
        pedi_precursors   = pedi_precursors,
        recommendation    = rec,
    )


def print_report(report: TelemetryReport) -> None:
    print("\n" + "="*68)
    print("PSC LIVE TELEMETRY VALIDATION REPORT")
    print("="*68)
    print(f"\n  Rows processed:      {report.total_rows}")
    print(f"  Sessions (est.):     ~{report.sessions_estimated}")
    print(f"  Policy:              {report.policy_used}")
    print(f"  Covered dimensions:  {len(report.covered_dims)}/{len(report.covered_dims)+len(report.sparse_dims)+len(report.missing_dims)}")
    print(f"  Sparse dims:         {report.sparse_dims or 'none'}")
    print(f"  Missing dims:        {report.missing_dims or 'none'}")

    print(f"\n  Total PSC alerts:    {report.alert_count}")
    hard   = sum(1 for a in report.alert_timeline if a["intensity"] == "hard")
    medium = sum(1 for a in report.alert_timeline if a["intensity"] == "medium")
    soft   = sum(1 for a in report.alert_timeline if a["intensity"] == "soft")
    print(f"    Hard:   {hard}")
    print(f"    Medium: {medium}")
    print(f"    Soft:   {soft}")

    if report.alert_timeline:
        print(f"\n  Alert timeline (first 10):")
        print(f"  {'Cycle':>7} {'Dim':<22} {'Current':>8} {'Predicted':>10} "
              f"{'Chaos':>7} {'Conf':>6} {'Intensity'}")
        print(f"  {'─'*75}")
        for a in report.alert_timeline[:10]:
            print(f"  {a['cycle']:>7} {a['dimension']:<22} {a['current']:>8.3f} "
                  f"{a['predicted']:>10.3f} {a['chaos']:>7.3f} "
                  f"{a['confidence']:>6.3f} {a['intensity']}")

    print(f"\n  Chaos distribution (covered dims):")
    print(f"  {'Dimension':<24} {'Mean':>6} {'Std':>6} {'p95':>6} {'Profile'}")
    print(f"  {'─'*55}")
    for dim, stats in sorted(report.chaos_distribution.items()):
        profile = (
            "HIGH VOLATILITY" if stats["mean"] > 0.55 else
            "MODERATE"        if stats["mean"] > 0.30 else
            "STABLE"
        )
        print(f"  {dim:<24} {stats['mean']:>6.3f} {stats['std']:>6.3f} "
              f"{stats['p95']:>6.3f} {profile}")

    print(f"\n  PEDI Precursor Signals (raw — no thresholds yet):")
    p = report.pedi_precursors
    print(f"    Alert rate:          {p['alert_rate_per_100_cycles']:.2f} per 100 cycles")
    print(f"    Mean ambient chaos:  {p['mean_chaos_across_dims']:.3f}")
    print(f"    Dim coverage:        {p['dim_coverage_fraction']:.0%}")
    print(f"    High-chaos dims:     {p['high_chaos_dim_count']}")
    print(f"    Note: {p['note']}")

    print(f"\n  Policy recommendation: {report.recommendation}")
    print("="*68)


def main():
    parser = argparse.ArgumentParser(
        description="PSC live telemetry validation against real being.db data"
    )
    parser.add_argument("--db",     default=DEFAULT_BEING_DB,
                        help="Path to being.db (default: being.db or DRIFT_BEING_DB env")
    parser.add_argument("--policy", default=DEFAULT_POLICY,
                        choices=["SECURITY", "BALANCED", "CONSERVATIVE"],
                        help="PSC policy mode")
    parser.add_argument("--limit",  type=int, default=DEFAULT_LIMIT,
                        help="Max rows to load from DB")
    parser.add_argument("--export", type=str, default=None,
                        help="Export full report as JSON to this path")
    args = parser.parse_args()

    print(f"[PSC Telemetry] Loading from: {args.db}")
    rows = load_being_db(args.db, limit=args.limit)

    if not rows:
        print("\n[INFO] No data found. Possible reasons:")
        print("  1. DRIFT hasn't run any sessions yet (memory_count=0 in health endpoint)")
        print("  2. being.db schema differs from expected — check DB table names above")
        print("  3. Wrong DB path — use --db or set DRIFT_BEING_DB env var")
        print("\n  Run DRIFT with a live Gemini key for 1-2 sessions, then re-run this script.")
        sys.exit(0)

    report = run_telemetry_validation(rows, policy=args.policy)
    print_report(report)

    if args.export:
        export_data = {
            "total_rows":          report.total_rows,
            "covered_dims":        report.covered_dims,
            "sparse_dims":         report.sparse_dims,
            "missing_dims":        report.missing_dims,
            "alert_count":         report.alert_count,
            "alert_timeline":      report.alert_timeline,
            "chaos_distribution":  report.chaos_distribution,
            "policy_used":         report.policy_used,
            "sessions_estimated":  report.sessions_estimated,
            "pedi_precursors":     report.pedi_precursors,
            "recommendation":      report.recommendation,
        }
        with open(args.export, "w") as f:
            json.dump(export_data, f, indent=2)
        print(f"\n[PSC] Report exported to {args.export}")


if __name__ == "__main__":
    main()
