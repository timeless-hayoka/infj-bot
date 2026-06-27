from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_dmu_retrieval_benchmark_smoke(tmp_path: Path) -> None:
    script = Path('/home/crexs/infj_bot/scripts/dmu_retrieval_benchmark.py')
    result = subprocess.run(
        [sys.executable, str(script), '--cases', '8', '--output-dir', str(tmp_path)],
        cwd='/home/crexs/infj_bot',
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )

    assert result.returncode == 0, result.stderr or result.stdout
    json_files = sorted(tmp_path.glob('dmu_retrieval_results_*.json'))
    csv_files = sorted(tmp_path.glob('dmu_retrieval_results_*.csv'))
    assert json_files, 'benchmark JSON output missing'
    assert csv_files, 'benchmark CSV output missing'

    payload = json.loads(json_files[-1].read_text(encoding='utf-8'))
    assert payload['summary']['cases'] == 8
    assert {'cosine', 'recent', 'dmu', 'guarded', 'rrf'}.issubset(set(payload['summary']['methods']))
    assert 'dmu_vs_cosine_context_delta_chars' in payload['summary']
    trace_root = tmp_path / 'score_traces' / 'v2_opaque_labels'
    assert trace_root.exists()
    assert list((trace_root / 'dmu').glob('case-*_dmu_*.json'))
    assert list((trace_root / 'guarded').glob('case-*_guarded_*.json'))
    assert list((trace_root / 'rrf').glob('case-*_rrf_*.json'))
