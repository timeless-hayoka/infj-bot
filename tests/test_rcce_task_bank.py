"""Validate the RCCE development task bank and independent scoring."""

import json
from pathlib import Path

from drift.core.rcce_scoring import score_response


def test_development_bank_has_balanced_unique_tasks():
    path = Path(__file__).parent / "data" / "rcce_dev_tasks_v1.json"
    tasks = json.loads(path.read_text())["tasks"]
    assert len(tasks) == 36
    assert len({t["id"] for t in tasks}) == 36
    for category in ("multi_step", "error_recovery", "instruction_following"):
        assert sum(t["category"] == category for t in tasks) == 12
    for task in tasks:
        assert task["prompt"].strip()
        assert task["expected"].strip()
        assert task["format"] in {"integer", "json_integer"}
        answer = (
            task["expected"]
            if task["format"] == "integer"
            else json.dumps({"answer": int(task["expected"])})
        )
        assert score_response(answer, task["expected"], task["format"]) == {
            "correct": True,
            "format_compliant": True,
        }


def test_default_live_smoke_covers_each_category(monkeypatch):
    from collections import Counter

    from rcce_live_ab_exploratory import load_tasks

    monkeypatch.delenv("RCCE_TASK_LIMIT", raising=False)
    assert Counter(task["category"] for task in load_tasks()) == {
        "multi_step": 2,
        "error_recovery": 2,
        "instruction_following": 2,
    }


def test_failed_live_trial_keeps_provider_status_without_raw_error(
    tmp_path, monkeypatch
):
    import rcce_live_ab_exploratory as live

    class ProviderError(Exception):
        code = 429

    def fail(output, run):
        run["active_trial"] = {"task_id": "test", "condition": "enabled"}
        try:
            raise ProviderError("sensitive provider request metadata")
        except ProviderError as exc:
            raise RuntimeError("RCCE_INVALID: critic inference failed") from exc

    path = tmp_path / "evidence.json"
    monkeypatch.setenv("RCCE_RESULTS_PATH", str(path))
    monkeypatch.setattr(live, "evaluate", fail)

    assert live.main() == 1
    raw = path.read_text()
    assert "sensitive provider request metadata" not in raw
    evidence = json.loads(raw)
    assert evidence["status"] == "failed"
    assert evidence["provider_http_status"] == 429
    assert evidence["active_trial"]["task_id"] == "test"
