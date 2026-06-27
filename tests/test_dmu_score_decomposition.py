from __future__ import annotations

import json
from pathlib import Path

from drift.core.dmu_score_decomposition import (
    attach_ranks,
    build_decomposition,
    compute_pure_semantic_ranks,
    serialize_traces,
)


def test_dmu_score_decomposition_serializes_traces(tmp_path: Path) -> None:
    traces = [
        build_decomposition(
            candidate_id='cand-1',
            cosine_similarity=0.81,
            recency_score=0.20,
            salience=0.70,
            retention_decay=0.55,
            emotional_weight=0.10,
            state_match=0.45,
            trust_level=0.90,
            conflict_penalty=0.00,
            final_dmu_score=0.92,
            memory_metadata={'id': 'cand-1', 'category': 'memory'},
        ),
        build_decomposition(
            candidate_id='cand-2',
            cosine_similarity=0.91,
            recency_score=0.10,
            salience=0.30,
            retention_decay=0.20,
            emotional_weight=0.05,
            state_match=0.15,
            trust_level=0.80,
            conflict_penalty=0.05,
            final_dmu_score=0.72,
            memory_metadata={'id': 'cand-2', 'category': 'noise'},
        ),
    ]

    ranked = attach_ranks(traces)
    compute_pure_semantic_ranks(ranked)
    path = serialize_traces(ranked, case_id='case-001', output_dir=tmp_path, timestamp='20260624_163048')

    payload = json.loads(path.read_text(encoding='utf-8'))
    assert payload['case_id'] == 'case-001'
    assert payload['num_candidates'] == 2
    assert payload['summary']['top_dmu_candidate'] == 'cand-1'
    assert payload['summary']['top_semantic_candidate'] == 'cand-2'
    assert payload['summary']['rank_disagreement'] is True
