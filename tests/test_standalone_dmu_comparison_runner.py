from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_standalone_dmu_comparison_runner_smoke(tmp_path: Path) -> None:
    script = Path("/home/crexs/infj_bot/scripts/standalone_dmu_comparison_runner.py")
    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--cases",
            "8",
            "--methods",
            "cosine,guarded_dmu,rrf",
            "--output-dir",
            str(tmp_path),
        ],
        cwd="/home/crexs/infj_bot",
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )

    assert result.returncode == 0, result.stderr or result.stdout
    json_files = sorted(tmp_path.glob("standalone_dmu_comparison_results_*.json"))
    csv_files = sorted(tmp_path.glob("standalone_dmu_comparison_results_*.csv"))
    assert json_files, "standalone runner JSON output missing"
    assert csv_files, "standalone runner CSV output missing"

    payload = json.loads(json_files[-1].read_text(encoding="utf-8"))
    assert payload["summary"]["cases"] == 8
    assert {"cosine", "guarded", "rrf"}.issubset(set(payload["summary"]["methods"]))
    trace_root = tmp_path / "score_traces" / "v2_opaque_labels"
    assert trace_root.exists()
    assert list((trace_root / "dmu").glob("case-*_dmu_*.json"))
    assert list((trace_root / "guarded").glob("case-*_guarded_*.json"))
    assert list((trace_root / "rrf").glob("case-*_rrf_*.json"))
