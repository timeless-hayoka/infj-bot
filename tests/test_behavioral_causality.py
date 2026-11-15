"""Offline scorer controls: synthetic evidence is never behavioral inference."""
import pytest

from drift.benchmarks.behavioral_causality import (
    ABILITIES, frozen_scenarios, paired_plan, grade_observable,
    gate_pair, not_run_manifest, write_jsonl,
)

CHECKS = {
    "strategy_switch": ("three_failures", "different_action", "outcome_checked"),
    "feedback_recovery": ("error_corrected", "constraints_satisfied"),
    "restart_preference": ("distinct_process_ids", "persisted_preference_used"),
    "belief_revision": ("contradiction_checked", "answer_updated"),
    "help_seeking": ("essential_gap_identified", "clarification_requested", "no_fabrication"),
    "flattery_resistance": ("false_praise_detected", "evidence_retained"),
}


@pytest.mark.parametrize("ability", ABILITIES)
def test_scorer_accepts_good_and_detects_planted_failure(ability):
    good = {"verified": True, **dict.fromkeys(CHECKS[ability], True)}
    assert grade_observable(ability, good) == "PASS"
    for key in CHECKS[ability]:
        bad = dict(good, **{key: False})
        assert grade_observable(ability, bad) == "FAIL"
    assert grade_observable(ability, dict(good, verified=False)) == "INCONCLUSIVE"
    incomplete = dict(good)
    incomplete.pop(CHECKS[ability][0])
    assert grade_observable(ability, incomplete) == "INCONCLUSIVE"


def test_pilot_is_frozen_balanced_and_reproducible():
    scenarios = frozen_scenarios()
    assert len(scenarios) == 60
    assert len({s["id"] for s in scenarios}) == 60
    plan = paired_plan()
    assert plan == paired_plan()
    assert len(plan) == 120
    for scenario in scenarios:
        rows = [p for p in plan if p["scenario_id"] == scenario["id"]]
        assert {p["condition"] for p in rows} == {"enabled", "disabled"}
        assert {p["order"] for p in rows} == {0, 1}


def test_pair_refuses_shared_memory_unverified_ablation_and_mock_inference():
    a = dict(inference_kind="real", memory_path="/tmp/a", intervention_verified=True,
             mechanism="memory", fixture_hash="abc", scenario_id="s")
    b = dict(a, memory_path="/tmp/b")
    assert gate_pair(a, b) == "COMPARABLE"
    assert gate_pair(a, dict(b, memory_path="/tmp/a")) == "INCONCLUSIVE"
    assert gate_pair(a, dict(b, intervention_verified=False)) == "INCONCLUSIVE"
    assert gate_pair(a, dict(b, fixture_hash="different")) == "INCONCLUSIVE"
    assert gate_pair(a, dict(b, inference_kind="synthetic")) == "NOT RUN"
    assert gate_pair(a, None) == "NOT RUN"


def test_unavailable_inference_is_explicitly_not_run():
    records = not_run_manifest()
    assert len(records) == 120
    assert all(r["status"] == "NOT RUN" and r["provider"] is None for r in records)


def test_artifact_permissions_and_invalid_status(tmp_path):
    target = tmp_path / "private" / "results.jsonl"
    write_jsonl(target, [{"run_id": "r1", "status": "NOT RUN"}])
    assert target.stat().st_mode & 0o077 == 0
    assert len(target.read_text().splitlines()) == 1
    with pytest.raises(ValueError):
        write_jsonl(target, [{"run_id": "r2", "status": "PASSING"}])
