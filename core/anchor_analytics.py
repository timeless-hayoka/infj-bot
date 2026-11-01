"""Load ANCHOR benchmark trends/strategy without duplicating math."""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from contextlib import contextmanager
from pathlib import Path
from threading import RLock
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
        if (resolved / "anchor_trends.py").exists() and (
            resolved / "benchmarks" / "index.json"
        ).exists():
            return resolved
    return None


_IMPORT_LOCK = RLock()


@contextmanager
def _analytics_modules(root: Path):
    # Canonical strategy imports canonical trends by name. Restore those aliases
    # afterwards, and never add the sibling checkout to the application's path.
    from core.anchor_context import _FreshSourceLoader

    names = ("anchor_trends", "anchor_strategy")
    with _IMPORT_LOCK:
        previous = {name: sys.modules.get(name) for name in names}
        modules = {}
        try:
            for name in names:
                source = root / f"{name}.py"
                spec = importlib.util.spec_from_file_location(
                    name, source, loader=_FreshSourceLoader(name, str(source))
                )
                if spec is None or spec.loader is None:
                    raise ImportError(f"Unable to load canonical analytics: {source}")
                module = importlib.util.module_from_spec(spec)
                sys.modules[name] = module
                spec.loader.exec_module(module)
                modules[name] = module
            yield modules
        finally:
            for name, module in previous.items():
                if module is None:
                    sys.modules.pop(name, None)
                else:
                    sys.modules[name] = module


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

    entries = load_anchor_manifest(root)
    outcomes = load_anchor_outcomes(root)
    with _analytics_modules(root) as modules:
        trends = modules["anchor_trends"].compute_benchmark_trends(
            entries, root=root, limit=limit
        )
        strategy = modules["anchor_strategy"].compute_strategy(
            entries,
            outcomes,
            root=root,
            trends_limit=limit,
            top_n=top_n,
        )
        sources = {
            name: str(Path(module.__file__).resolve())
            for name, module in modules.items()
        }
    return {
        "status": "ready",
        "anchor_root": str(root),
        "analytics_sources": sources,
        "benchmark_trends": trends,
        "benchmark_strategy": strategy,
    }
