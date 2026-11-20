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
        answer = task["expected"] if task["format"] == "integer" else json.dumps({"answer": int(task["expected"])})
        assert score_response(answer, task["expected"], task["format"]) == {
            "correct": True, "format_compliant": True,
        }
