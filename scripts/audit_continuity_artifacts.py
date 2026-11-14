"""Independently verify arithmetic and coverage of saved continuity JSON artifacts.

This does not replay model calls or regrade responses without raw answers.
Usage: python scripts/audit_continuity_artifacts.py /path/to/artifacts
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


FIELDS = ("preference", "workspace", "format", "day", "completed", "next", "reviewer")


def read_json(folder: Path, name: str):
    return json.loads((folder / name).read_text(encoding="utf-8"))


def verify(folder: Path) -> dict:
    summary = read_json(folder, "summary.json")
    audit = read_json(folder, "audit.json")
    midpoint = read_json(folder, "midpoint-audit.json")
    scenarios = read_json(folder, "scenarios.json")
    rules = read_json(folder, "scoring-rules.json")
    rules_copy = read_json(folder, "scoring-rules(1).json")
    metadata = read_json(folder, "metadata.json")

    errors = []
    def check(condition: bool, message: str) -> None:
        if not condition:
            errors.append(message)

    n = len(scenarios)
    check(n == summary["pairs"] == audit["pairs"], "scenario/pair count mismatch")
    check(len({item["name"] for item in scenarios}) == n, "duplicate scenario names")
    check(all(tuple(item["expected"]) == FIELDS for item in scenarios), "expected fields differ")
    check(rules == rules_copy, "scoring rules copies differ")
    check(summary == audit["summary"], "audit and summary mismatch")
    check(summary["possible_points_per_condition"] == n * len(FIELDS), "incorrect denominator")
    check(summary["improved"] + summary["tied"] + summary["regressed"] == n,
          "paired outcomes do not total number of scenarios")
    check(summary["paired_on_minus_off"] == summary["points"]["on"] - summary["points"]["off"],
          "reported score difference mismatch")
    check(abs(summary["mean_paired_difference"] * n - summary["paired_on_minus_off"]) < 1e-9,
          "mean paired difference mismatch")
    for condition in ("on", "off"):
        counts = summary["correct_by_field"][condition]
        check(set(counts) == set(FIELDS), f"{condition}: field set mismatch")
        check(all(isinstance(v, int) and 0 <= v <= n for v in counts.values()),
              f"{condition}: field count out of bounds")
        check(sum(counts.values()) == summary["points"][condition],
              f"{condition}: field counts do not sum to points")
        check(0 <= summary["all_seven_correct"][condition] <= min(counts.values()),
              f"{condition}: impossible all-seven count")
    check(midpoint["completed_pairs"] <= n, "midpoint exceeds full sample")
    check(audit["actual_generation_calls"] >= n * 2,
          "reported generation calls below number of primary comparisons")
    check(metadata["options"]["seed"] == audit["request_settings_all_match"]["seed"],
          "seed mismatch between metadata and audit")
    check(metadata["model"]["digest"] == audit["model_digest_all_calls"],
          "model digest mismatch")
    check(all(item["expected"]["reviewer"] is None for item in scenarios),
          "reviewer is not always an abstention; adjust interpretation")

    useful = {}
    for condition in ("on", "off"):
        counts = summary["correct_by_field"][condition]
        useful[condition] = {
            "non_abstention_correct": sum(counts[k] for k in FIELDS if k != "reviewer"),
            "non_abstention_possible": n * (len(FIELDS) - 1),
            "preference_correct": counts["preference"],
            "supersession_correct": counts["day"],
            "task_completed_correct": counts["completed"],
            "task_next_correct": counts["next"],
        }
    return {
        "ok": not errors,
        "errors": errors,
        "pairs": n,
        "reported_generation_calls_not_independently_verified": audit["actual_generation_calls"],
        "raw_responses_present": False,
        "independent_regrading_possible": False,
        "useful_recall": useful,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("folder", type=Path)
    args = parser.parse_args()
    report = verify(args.folder)
    print(json.dumps(report, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
