#!/usr/bin/env python3
"""DMU score decomposition instrumentation.

This module records per-candidate score breakdowns for DMU-style ranking
without changing the underlying retrieval behavior. It is intentionally
standalone so benchmark harnesses and offline analyses can serialize traces
without pulling in the full ranking stack.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class DMUScoreDecomposition:
    """Structured, JSON-serializable record of one candidate's ranking score."""

    candidate_id: str
    cosine_similarity: float
    recency_score: float
    salience: float
    retention_decay_score: float
    emotional_weight: float
    state_match_score: float
    trust_level: float
    conflict_penalty: float
    final_dmu_score: float
    rank: int = 0
    semantic_rank: Optional[int] = None
    memory_metadata: Dict[str, Any] = field(default_factory=dict)
    notes: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        if not isinstance(payload.get("memory_metadata"), dict):
            payload["memory_metadata"] = {}
        return payload


def build_decomposition(
    *,
    candidate_id: str,
    cosine_similarity: float,
    recency_score: float,
    salience: float,
    retention_decay: float,
    emotional_weight: float,
    state_match: float,
    trust_level: float,
    conflict_penalty: float,
    final_dmu_score: float,
    memory_metadata: Optional[Dict[str, Any]] = None,
    notes: str = "",
) -> DMUScoreDecomposition:
    """Create a validated decomposition record."""
    return DMUScoreDecomposition(
        candidate_id=str(candidate_id),
        cosine_similarity=float(cosine_similarity),
        recency_score=float(recency_score),
        salience=float(salience),
        retention_decay_score=float(retention_decay),
        emotional_weight=float(emotional_weight),
        state_match_score=float(state_match),
        trust_level=float(trust_level),
        conflict_penalty=float(conflict_penalty),
        final_dmu_score=float(final_dmu_score),
        memory_metadata=memory_metadata or {},
        notes=notes,
    )


def attach_ranks(
    decompositions: List[DMUScoreDecomposition],
    *,
    sort_key: str = "final_dmu_score",
    descending: bool = True,
) -> List[DMUScoreDecomposition]:
    """Assign DMU ranks based on the chosen score key."""
    sorted_decomps = sorted(decompositions, key=lambda d: getattr(d, sort_key), reverse=descending)
    for idx, decomp in enumerate(sorted_decomps, start=1):
        decomp.rank = idx
    return sorted_decomps


def compute_pure_semantic_ranks(
    decompositions: List[DMUScoreDecomposition],
) -> List[DMUScoreDecomposition]:
    """Annotate each decomposition with its pure cosine rank."""
    sorted_by_cosine = sorted(decompositions, key=lambda d: d.cosine_similarity, reverse=True)
    for idx, decomp in enumerate(sorted_by_cosine, start=1):
        decomp.semantic_rank = idx
    return decompositions


def serialize_traces(
    traces: List[DMUScoreDecomposition],
    *,
    case_id: str,
    output_dir: str | Path,
    timestamp: Optional[str] = None,
    method: str = "dmu",
) -> Path:
    """Write one per-case trace bundle to disk."""
    if timestamp is None:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    filepath = out_dir / f"{case_id}_{method}_{timestamp}.json"

    if any(d.rank == 0 for d in traces):
        traces = attach_ranks(traces)
    traces = compute_pure_semantic_ranks(traces)

    payload = {
        "case_id": case_id,
        "method": method,
        "timestamp": timestamp,
        "num_candidates": len(traces),
        "decompositions": [d.to_dict() for d in traces],
        "summary": {
            "top_dmu_candidate": traces[0].candidate_id if traces else None,
            "top_dmu_score": traces[0].final_dmu_score if traces else None,
            "top_semantic_candidate": next((d.candidate_id for d in traces if d.semantic_rank == 1), None),
            "top_semantic_score": next((d.cosine_similarity for d in traces if d.semantic_rank == 1), None),
            "rank_disagreement": any(d.rank != d.semantic_rank for d in traces if d.semantic_rank is not None),
        },
    }

    filepath.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    return filepath


if __name__ == "__main__":
    print("DMU score decomposition module ready.")
