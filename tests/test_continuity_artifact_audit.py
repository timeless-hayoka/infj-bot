"""Regression tests for continuity artifact auditing."""
import copy
import json

from scripts.audit_continuity_artifacts import FIELDS, verify


def fixture(tmp_path):
    scenario = {"name": "Alder", "expected": dict.fromkeys(FIELDS)}
    scenario["expected"].update({"preference": "bullets", "workspace": "lab"})
    counts_on = dict.fromkeys(FIELDS, 0)
    counts_off = dict.fromkeys(FIELDS, 0)
    counts_on["workspace"] = 1
    counts_on["reviewer"] = 1
    counts_off["reviewer"] = 1
    summary = {
        "pairs": 1, "possible_points_per_condition": 7,
        "points": {"on": 2, "off": 1},
        "paired_on_minus_off": 1, "mean_paired_difference": 1,
        "improved": 1, "tied": 0, "regressed": 0,
        "correct_by_field": {"on": counts_on, "off": counts_off},
        "all_seven_correct": {"on": 0, "off": 0},
    }
    data = {
        "scenarios.json": [scenario],
        "summary.json": summary,
        "audit.json": {"pairs": 1, "summary": copy.deepcopy(summary),
                       "actual_generation_calls": 14,
                       "request_settings_all_match": {"seed": 42},
                       "model_digest_all_calls": "digest"},
        "midpoint-audit.json": {"completed_pairs": 1},
        "scoring-rules.json": {"rule": "strict"},
        "scoring-rules(1).json": {"rule": "strict"},
        "metadata.json": {"options": {"seed": 42}, "model": {"digest": "digest"}},
    }
    for filename, value in data.items():
        (tmp_path / filename).write_text(json.dumps(value))
    return data


def test_valid_fixture_reconciles(tmp_path):
    fixture(tmp_path)
    report = verify(tmp_path)
    assert report["ok"], report["errors"]
    assert report["useful_recall"]["on"]["non_abstention_correct"] == 1
    assert report["useful_recall"]["off"]["non_abstention_correct"] == 0
    assert not report["independent_regrading_possible"]


def test_inflated_points_are_detected(tmp_path):
    data = fixture(tmp_path)
    data["summary.json"]["points"]["on"] = 3
    (tmp_path / "summary.json").write_text(json.dumps(data["summary.json"]))
    report = verify(tmp_path)
    assert not report["ok"]
    assert any("field counts" in error for error in report["errors"])


def test_model_identity_mismatch_is_detected(tmp_path):
    data = fixture(tmp_path)
    data["metadata.json"]["model"]["digest"] = "different"
    (tmp_path / "metadata.json").write_text(json.dumps(data["metadata.json"]))
    report = verify(tmp_path)
    assert not report["ok"]
    assert any("digest" in error for error in report["errors"])
