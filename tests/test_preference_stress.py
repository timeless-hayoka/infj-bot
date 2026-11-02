"""Detector must pass real prompt assembly and reject an injected stale directive."""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "preference_stress", ROOT / "tests/preference_stress_runner.py"
)
harness = importlib.util.module_from_spec(spec)
spec.loader.exec_module(harness)


def test_real_preference_read_path_and_planted_stale(tmp_path):
    good = harness.exercise(tmp_path / "good")
    bad = harness.exercise(tmp_path / "bad", plant_stale=True)
    assert good["verdict"] == "PASS", good
    assert len(good["turns"]) == 5
    assert bad["verdict"] == "FAIL", bad
    assert any(row["stale_hits"] and row["prompt_diff"] for row in bad["turns"][2:])
    assert any(
        "[CONSTRAINT] output_style=concise_bullets" in row["stale_hits"]
        for row in bad["turns"]
    )
    rows = [
        json.loads(line)
        for line in (tmp_path / "bad/trajectory.jsonl").read_text().splitlines()
    ]
    assert len(rows) == 5
    assert rows[2]["metadata"]["stale_hits"]
    assert rows[2]["timing"]["infer_cpu_ms"] is None


def test_cli_inconclusive_is_nonzero(tmp_path):
    # An output path that is a file makes setup impossible; it must never PASS.
    invalid = tmp_path / "not-a-directory"
    invalid.write_text("occupied")
    result = subprocess.run(
        check=False,
        args=[
            sys.executable,
            str(ROOT / "tests/preference_stress_runner.py"),
            "--output-dir",
            str(invalid),
        ],
        text=True,
        capture_output=True,
        timeout=60,
    )
    assert result.returncode == 2
    assert "INCONCLUSIVE" in result.stderr
