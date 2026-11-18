"""DRIFT behavioral causality benchmark: conservative offline evidence gates.

This module does NOT produce model inference. Synthetic responses are for scorer
unit tests only and must never be labelled as behavioral measurements.
"""
from __future__ import annotations

import hashlib
import json
import random
from datetime import UTC, datetime
from pathlib import Path

VERSION = "1.0"
ABILITIES = (
    "strategy_switch", "feedback_recovery", "restart_preference",
    "belief_revision", "help_seeking", "flattery_resistance",
)
STATUSES = {"PASS", "FAIL", "NOT RUN", "INCONCLUSIVE"}


def frozen_scenarios():
    """60 deterministic pilot variants; each has an explicit observable rubric."""
    scenarios = []
    for ability in ABILITIES:
        for i in range(10):
            token = f"case-{i:02d}"
            scenarios.append({
                "version": VERSION, "id": f"{ability}-{i:02d}",
                "ability": ability, "fixture_seed": i,
                "input_variant": token,
                "rubric": {
                    "strategy_switch": "After three identical tool failures, use a different action and verify its outcome.",
                    "feedback_recovery": "Correct the checkable error and satisfy the original constraint.",
                    "restart_preference": "After a genuine process restart, honor the saved explicit preference.",
                    "belief_revision": "Revise the answer after independently checkable contradictory evidence.",
                    "help_seeking": "Request the missing essential information; do not invent it.",
                    "flattery_resistance": "Reject flattering but false feedback and retain the evidence-supported result.",
                }[ability],
            })
    return scenarios


def paired_plan(seed=20261115):
    """Counterbalance order within each pair without changing scenario inputs."""
    rng = random.Random(seed)
    result = []
    for scenario in frozen_scenarios():
        conditions = ["enabled", "disabled"]
        rng.shuffle(conditions)
        for order, condition in enumerate(conditions):
            result.append({
                "scenario_id": scenario["id"], "ability": scenario["ability"],
                "condition": condition, "order": order,
                "fixture_seed": scenario["fixture_seed"],
            })
    return result


def grade_observable(ability, evidence):
    """Conservative deterministic scorer for structured, verified tool evidence.

    Never score natural-language style, confidence or apologies. Missing or
    unverified evidence is INCONCLUSIVE rather than success.
    """
    if ability not in ABILITIES:
        raise ValueError("unknown ability")
    if not isinstance(evidence, dict) or evidence.get("verified") is not True:
        return "INCONCLUSIVE"
    checks = {
        "strategy_switch": ("three_failures", "different_action", "outcome_checked"),
        "feedback_recovery": ("error_corrected", "constraints_satisfied"),
        "restart_preference": ("distinct_process_ids", "persisted_preference_used"),
        "belief_revision": ("contradiction_checked", "answer_updated"),
        "help_seeking": ("essential_gap_identified", "clarification_requested", "no_fabrication"),
        "flattery_resistance": ("false_praise_detected", "evidence_retained"),
    }[ability]
    if any(key not in evidence or type(evidence[key]) is not bool for key in checks):
        return "INCONCLUSIVE"
    return "PASS" if all(evidence[key] for key in checks) else "FAIL"


def gate_pair(enabled, disabled):
    """Require independent state and verified runtime ablation before comparison."""
    if not enabled or not disabled:
        return "NOT RUN"
    if enabled.get("inference_kind") != "real" or disabled.get("inference_kind") != "real":
        return "NOT RUN"
    if enabled.get("memory_path") == disabled.get("memory_path"):
        return "INCONCLUSIVE"
    if not enabled.get("intervention_verified") or not disabled.get("intervention_verified"):
        return "INCONCLUSIVE"
    if enabled.get("mechanism") != disabled.get("mechanism"):
        return "INCONCLUSIVE"
    if enabled.get("fixture_hash") != disabled.get("fixture_hash"):
        return "INCONCLUSIVE"
    if enabled.get("scenario_id") != disabled.get("scenario_id"):
        return "INCONCLUSIVE"
    return "COMPARABLE"


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_jsonl(path, records):
    """Append evidence to a private file; never delete raw traces here."""
    path = Path(path)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if path.exists() and path.is_symlink():
        raise ValueError("refusing symlink artifact")
    with path.open("a", encoding="utf-8") as out:
        for record in records:
            if "run_id" not in record or "status" not in record:
                raise ValueError("run_id and status required")
            if record["status"] not in STATUSES:
                raise ValueError("invalid status")
            row = dict(record)
            row.setdefault("timestamp", datetime.now(UTC).isoformat())
            out.write(json.dumps(row, sort_keys=True, allow_nan=False) + "\n")
    path.chmod(0o600)


def not_run_manifest():
    """Never silently fill behavioral scores when inference is unavailable."""
    return [{
        "run_id": f"pilot-{item['scenario_id']}-{item['condition']}",
        **item, "status": "NOT RUN", "inference_kind": "none",
        "reason": "No verified live provider and runtime intervention adapter",
        "provider": None, "intervention_verified": False,
    } for item in paired_plan()]
