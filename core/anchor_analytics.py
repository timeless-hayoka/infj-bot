"""Load ANCHOR benchmark trends/strategy without duplicating math."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def resolve_anchor_root() -> Path | None:
    candidates: list[Path] = []
    if os.environ.get("ANCHOR_ROOT"):
        candidates.append(Path(os.environ["ANCHOR_ROOT"]))
    candidates.append(ROOT.parent / "ANCHOR")
    candidates.append(ROOT / "ANCHOR")
    for path in candidates:
        resolved = path.resolve()
        if (resolved / "anchor_trends.py").exists() and (resolved / "benchmarks" / "index.json").exists():
            return resolved
    return None


def _ensure_anchor_import(root: Path) -> None:
    root_str = str(root)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)


def load_anchor_manifest(root: Path) -> list[dict[str, Any]]:
    manifest_path = root / "benchmarks" / "index.json"
    if not manifest_path.exists():
        return []
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    entries = payload.get("benchmarks", [])
    return entries if isinstance(entries, list) else []


def load_anchor_outcomes(root: Path) -> list[dict[str, Any]]:
    ledger_path = root / "outcomes" / "ledger.jsonl"
    if not ledger_path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in ledger_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            row = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def build_benchmark_analytics(*, limit: int = 10, top_n: int = 5) -> dict[str, Any]:
    root = resolve_anchor_root()
    if root is None:
        return {
            "status": "unavailable",
            "reason": "ANCHOR repo not found (set ANCHOR_ROOT or clone sibling ANCHOR/)",
            "benchmark_trends": None,
            "benchmark_strategy": None,
        }

    _ensure_anchor_import(root)
    from anchor_strategy import compute_strategy
    from anchor_trends import compute_benchmark_trends

    entries = load_anchor_manifest(root)
    outcomes = load_anchor_outcomes(root)
    trends = compute_benchmark_trends(entries, root=root, limit=limit)
    strategy = compute_strategy(
        entries,
        outcomes,
        root=root,
        trends_limit=limit,
        top_n=top_n,
    )
    return {
        "status": "ready",
        "anchor_root": str(root),
        "benchmark_trends": trends,
        "benchmark_strategy": strategy,
    }
