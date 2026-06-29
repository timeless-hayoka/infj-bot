#!/usr/bin/env python3
"""Export synthetic DMU benchmark cases to JSON for Chroma-backed evaluation."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = Path(__file__).resolve().parent
for candidate in (str(SCRIPTS_DIR), str(ROOT)):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

from dmu_retrieval_benchmark import build_dataset


def export_dataset(
    output_path: Path,
    *,
    cases: int = 100,
    dataset_version: str = "v2_opaque_labels",
) -> Path:
    benchmark_cases, _memories = build_dataset(cases, dataset_version=dataset_version)
    rows = []
    for case in benchmark_cases:
        row = asdict(case)
        row["psc_alert_dims"] = list(row.get("psc_alert_dims") or ())
        row["gold_memory_id"] = case.correct_memory_id
        rows.append(row)

    payload = {
        "dataset_version": dataset_version,
        "cases": rows,
    }
    output_path = output_path.expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return output_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Export DMU benchmark cases to JSON.")
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "benchmarks" / "v2_opaque_labels" / "dataset.json",
        help="Destination JSON path",
    )
    parser.add_argument("--cases", type=int, default=100)
    parser.add_argument(
        "--dataset-version",
        choices=("v1_label_leakage", "v2_opaque_labels"),
        default="v2_opaque_labels",
    )
    args = parser.parse_args()
    path = export_dataset(args.output, cases=args.cases, dataset_version=args.dataset_version)
    print(f"Wrote {len(json.loads(path.read_text())['cases'])} cases to {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
