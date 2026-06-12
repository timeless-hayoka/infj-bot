#!/usr/bin/env python3
"""
Offline JSONL analyzer — runs locally, NOT on the inference droplet.

Copy logs down with ``sync_logs.py`` (or ``scp``) and analyze here.

Usage:
    python scripts/analyze_jsonl.py logs/security_audit.jsonl --tail 50
    python scripts/analyze_jsonl.py logs/*.jsonl --since 2026-06-01 --summary
    python scripts/analyze_jsonl.py logs/tool_audit.jsonl --field status --hist

Design goals (from operator feedback):
  - Per-line try/except: one corrupt line never kills the whole analysis.
  - No Streamlit, no plotly, no extra ports — CLI-only, runs on your laptop.
  - Fast enough for multi-megabyte files.
"""

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Iterator, Optional


def _read_jsonl_fault_tolerant(path: Path) -> Iterator[dict]:
    """Yield decoded objects; skip corrupt lines silently."""
    if not path.exists():
        return
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except Exception:
                continue


def _get_ts(record: dict) -> Optional[str]:
    return record.get("ts") or record.get("timestamp")


def _parse_since(s: str) -> str:
    """Accept ISO date or full timestamp; normalise to comparable string."""
    s = s.strip()
    if "T" in s:
        return s
    return f"{s}T00:00:00"


def tail(paths: list[Path], n: int) -> None:
    records: list[tuple[Path, dict]] = []
    for p in paths:
        for rec in _read_jsonl_fault_tolerant(p):
            records.append((p, rec))
    for p, rec in records[-n:]:
        ts = _get_ts(rec) or "?"
        print(f"[{p.name}] {ts}  {json.dumps(rec, default=str)[:200]}")


def summary(paths: list[Path], since: Optional[str] = None) -> None:
    total = 0
    valid = 0
    corrupt = 0
    per_file: dict[str, int] = {}
    timestamps: list[str] = []

    for p in paths:
        file_total = 0
        for rec in _read_jsonl_fault_tolerant(p):
            valid += 1
            file_total += 1
            ts = _get_ts(rec)
            if ts:
                timestamps.append(ts)
        # Corrupt estimate: raw line count minus valid decoded lines
        try:
            raw_lines = sum(1 for _ in open(p, "r", encoding="utf-8", errors="replace"))
        except Exception:
            raw_lines = 0
        file_corrupt = max(0, raw_lines - file_total)
        corrupt += file_corrupt
        total += raw_lines
        per_file[p.name] = file_total

    print(f"Files analyzed: {len(paths)}")
    print(f"Total lines:    {total}")
    print(f"Valid records:  {valid}")
    print(f"Corrupt lines:  {corrupt}")
    if timestamps:
        print(f"Date range:     {min(timestamps)[:19]} -> {max(timestamps)[:19]}")
    print("\nPer-file counts:")
    for name, cnt in sorted(per_file.items(), key=lambda x: -x[1]):
        print(f"  {name:40s} {cnt:>8d}")


def field_hist(paths: list[Path], field: str, top: int = 20) -> None:
    counter: Counter[str] = Counter()
    for p in paths:
        for rec in _read_jsonl_fault_tolerant(p):
            val = rec.get(field)
            if val is not None:
                counter[str(val)] += 1
    print(f"Top {top} values for field '{field}':")
    for val, cnt in counter.most_common(top):
        print(f"  {cnt:>6d}  {val}")


def stream_since(paths: list[Path], since: str) -> None:
    since_norm = _parse_since(since)
    for p in paths:
        for rec in _read_jsonl_fault_tolerant(p):
            ts = _get_ts(rec)
            if ts and ts >= since_norm:
                print(json.dumps(rec, default=str))


def main() -> None:
    parser = argparse.ArgumentParser(description="Offline JSONL analyzer")
    parser.add_argument("paths", nargs="+", type=Path, help="JSONL file(s)")
    parser.add_argument("--tail", type=int, metavar="N", help="Show last N records")
    parser.add_argument("--since", type=str, metavar="DATE", help="ISO date/time filter")
    parser.add_argument("--summary", action="store_true", help="Print aggregate stats")
    parser.add_argument("--field", type=str, metavar="KEY", help="Field to histogram")
    parser.add_argument("--hist", action="store_true", help="Show histogram for --field")
    args = parser.parse_args()

    if args.tail:
        tail(args.paths, args.tail)
    elif args.hist and args.field:
        field_hist(args.paths, args.field)
    elif args.summary:
        summary(args.paths, since=args.since)
    elif args.since:
        stream_since(args.paths, args.since)
    else:
        # Default: dump everything (one JSON per line) — pipe-friendly
        for p in args.paths:
            for rec in _read_jsonl_fault_tolerant(p):
                print(json.dumps(rec, default=str))


if __name__ == "__main__":
    main()
