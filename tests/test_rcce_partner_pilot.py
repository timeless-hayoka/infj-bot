import json
import sqlite3
import subprocess
import sys

import rcce_partner_pilot as pilot


def test_restart_and_matched_replay(tmp_path):
    root = tmp_path / "stores"
    subprocess.run([sys.executable, pilot.__file__, "prepare", str(root)], check=True)
    manifest = json.loads((root / "training.json").read_text())
    assert len(set(manifest["stores"].values())) == 2
    assert len(list(pilot.planned_trials(root))) == 54
    cases = {}
    for row, prompt in pilot.planned_trials(root):
        cases.setdefault((row["task_id"], row["partner"]), {})[row["condition"]] = (
            row,
            prompt,
        )
    for (_, partner), conditions in cases.items():
        restored, restored_prompt = conditions["restored"]
        swapped, _ = conditions["swapped"]
        replay, replay_prompt = conditions["replay"]
        assert restored["source"] == replay["source"] == partner
        assert swapped["source"] != partner
        assert restored["history_sha256"] == replay["history_sha256"]
        assert restored["history_sha256"] != swapped["history_sha256"]
        assert restored["recommendation"] != swapped["recommendation"]
        assert restored["expected"] == swapped["expected"] == replay["expected"]
        assert (
            restored_prompt.replace(
                f"Recommendation: {restored['recommendation']}", "Recommendation: infer"
            )
            == replay_prompt
        )
    for partner in pilot.PARTNERS:
        with sqlite3.connect(root / f"{partner}.sqlite") as conn:
            tasks = conn.execute("SELECT task FROM rcce_principle_outcomes").fetchall()
        assert len(tasks) == 6
        assert all(task.startswith("training-") for (task,) in tasks)


def test_each_task_distinguishes_the_two_partners():
    for task in pilot.TASKS:
        assert pilot.expected_answer(task, "P1") != pilot.expected_answer(task, "P2")
