#!/usr/bin/env python3
"""Alternative ranking algorithms for DMU-style memory retrieval.

These rankers are compatible with DMU score decomposition and can be used
as baselines or safer replacements when the original DMU weighting is too
aggressive.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from drift.core.dmu_score_decomposition import (
    DMUScoreDecomposition,
    attach_ranks,
    build_decomposition,
    compute_pure_semantic_ranks,
)

QueryContext = Dict[str, Any]
MemoryCandidate = Dict[str, Any]


def _safe_cosine(a: List[float], b: List[float]) -> float:
    if not a or not b:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        return 0.0
    return max(min(dot / (na * nb), 1.0), -1.0)


def _default_signal_extractors() -> Dict[str, Callable[[MemoryCandidate, QueryContext], float]]:
    def recency(cand: MemoryCandidate, ctx: QueryContext) -> float:
        ts = cand.get("timestamp", 0)
        now = ctx.get("current_time", ts)
        age_hours = max(0.0, (now - ts) / 3600.0)
        return math.exp(-age_hours / 168.0)

    def salience(cand: MemoryCandidate, ctx: QueryContext) -> float:
        return float(cand.get("salience", 0.5))

    def retention(cand: MemoryCandidate, ctx: QueryContext) -> float:
        return float(cand.get("retention_score", cand.get("retention_decay", 0.8)))

    def emotional(cand: MemoryCandidate, ctx: QueryContext) -> float:
        valence = abs(float(cand.get("emotional_valence", 0.0)))
        intensity = float(cand.get("emotional_intensity", 0.5))
        return min(1.0, valence * 0.6 + intensity * 0.4)

    def state_match(cand: MemoryCandidate, ctx: QueryContext) -> float:
        return float(cand.get("state_match", 0.6))

    def trust(cand: MemoryCandidate, ctx: QueryContext) -> float:
        return float(cand.get("trust_level", 0.75))

    def conflict_penalty(cand: MemoryCandidate, ctx: QueryContext) -> float:
        if cand.get("has_conflict", False) or cand.get("conflict_status") == "unresolved":
            return 0.25
        return 0.0

    return {
        "recency": recency,
        "salience": salience,
        "retention": retention,
        "emotional": emotional,
        "state_match": state_match,
        "trust": trust,
        "conflict": conflict_penalty,
    }


@dataclass
class GuardedWeightedRanker:
    weights: Dict[str, float] = field(default_factory=lambda: {
        "cosine": 0.55,
        "recency": 0.12,
        "salience": 0.10,
        "retention": 0.08,
        "emotional": 0.07,
        "state_match": 0.04,
        "trust": 0.03,
        "conflict": -0.05,
    })
    semantic_weight: float = 0.70
    guardrail_threshold: float = 0.08
    signal_extractors: Optional[Dict[str, Callable]] = None

    def __post_init__(self):
        if self.signal_extractors is None:
            self.signal_extractors = _default_signal_extractors()

    def _compute_score(self, cand: MemoryCandidate, ctx: QueryContext, query_emb: List[float]) -> Tuple[float, Dict[str, float]]:
        components: Dict[str, float] = {}
        mem_emb = cand.get("embedding", [])
        cos = _safe_cosine(query_emb, mem_emb)
        components["cosine_similarity"] = cos

        for name, extractor in self.signal_extractors.items():
            components[name] = extractor(cand, ctx)

        score = self.weights.get("cosine", 0.55) * cos
        for name, w in self.weights.items():
            if name == "cosine":
                continue
            score += w * components.get(name, 0.0)

        components["final_dmu_score"] = score
        return score, components

    def rank(
        self,
        candidates: List[MemoryCandidate],
        query_context: QueryContext,
        *,
        query_embedding: Optional[List[float]] = None,
        top_k: int = 5,
        return_decompositions: bool = True,
    ) -> Tuple[List[MemoryCandidate], List[DMUScoreDecomposition]]:
        if not candidates:
            return [], []

        q_emb = query_embedding or query_context.get("query_embedding", [])
        if not q_emb:
            q_emb = candidates[0].get("query_embedding", [])

        scored: List[Tuple[float, MemoryCandidate, Dict[str, float]]] = []
        best_cosine = -1.0

        for cand in candidates:
            score, comps = self._compute_score(cand, query_context, q_emb)
            scored.append((score, cand, comps))
            best_cosine = max(best_cosine, comps["cosine_similarity"])

        guarded_scored = []
        for score, cand, comps in scored:
            cos = comps["cosine_similarity"]
            if cos < best_cosine - self.guardrail_threshold:
                score -= 10.0
                comps["final_dmu_score"] = score
                comps["notes"] = f"GUARDRAIL_APPLIED (cosine {cos:.4f} vs best {best_cosine:.4f})"
            guarded_scored.append((score, cand, comps))

        guarded_scored.sort(key=lambda x: x[0], reverse=True)
        ranked_cands = [c for _, c, _ in guarded_scored][:top_k]

        if not return_decompositions:
            return ranked_cands, []

        decomps: List[DMUScoreDecomposition] = []
        for rank_idx, (score, cand, comps) in enumerate(guarded_scored, start=1):
            decomp = build_decomposition(
                candidate_id=str(cand.get("id", cand.get("memory_id", f"mem_{rank_idx}"))),
                cosine_similarity=comps["cosine_similarity"],
                recency_score=comps.get("recency", 0.0),
                salience=comps.get("salience", 0.0),
                retention_decay=comps.get("retention", 0.0),
                emotional_weight=comps.get("emotional", 0.0),
                state_match=comps.get("state_match", 0.0),
                trust_level=comps.get("trust", 0.0),
                conflict_penalty=comps.get("conflict", 0.0),
                final_dmu_score=comps["final_dmu_score"],
                memory_metadata=cand,
                notes=comps.get("notes", ""),
            )
            decomp.rank = rank_idx
            decomps.append(decomp)

        decomps = compute_pure_semantic_ranks(decomps)
        return ranked_cands, decomps


@dataclass
class ReciprocalRankFusionRanker:
    k: int = 60
    signal_rankers: Optional[List[Tuple[str, Callable]]] = None
    cosine_first_stage_k: int = 50

    def __post_init__(self):
        if self.signal_rankers is None:
            self.signal_rankers = [
                ("cosine", self._cosine_ranker),
                ("recency", self._recency_ranker),
                ("salience", self._salience_ranker),
            ]

    def _cosine_ranker(self, cands: List[MemoryCandidate], ctx: QueryContext) -> List[Tuple[float, MemoryCandidate]]:
        q_emb = ctx.get("query_embedding", [])
        scored = [(_safe_cosine(q_emb, c.get("embedding", [])), c) for c in cands]
        scored.sort(key=lambda x: x[0], reverse=True)
        return scored

    def _recency_ranker(self, cands: List[MemoryCandidate], ctx: QueryContext) -> List[Tuple[float, MemoryCandidate]]:
        scored = [(float(c.get("timestamp", 0)), c) for c in cands]
        scored.sort(key=lambda x: x[0], reverse=True)
        return scored

    def _salience_ranker(self, cands: List[MemoryCandidate], ctx: QueryContext) -> List[Tuple[float, MemoryCandidate]]:
        scored = [(float(c.get("salience", 0.5)), c) for c in cands]
        scored.sort(key=lambda x: x[0], reverse=True)
        return scored

    def rank(
        self,
        candidates: List[MemoryCandidate],
        query_context: QueryContext,
        *,
        top_k: int = 5,
        return_decompositions: bool = True,
    ) -> Tuple[List[MemoryCandidate], List[DMUScoreDecomposition]]:
        if not candidates:
            return [], []

        first_stage = self._cosine_ranker(candidates, query_context)[: self.cosine_first_stage_k]
        first_stage_cands = [c for _, c in first_stage]
        if len(first_stage_cands) < 2:
            return first_stage_cands[:top_k], []

        signal_ranks: Dict[str, Dict[str, int]] = {}
        for name, ranker_fn in self.signal_rankers:
            ranked = ranker_fn(first_stage_cands, query_context)
            signal_ranks[name] = {str(c.get("id", id(c))): rank + 1 for rank, (_, c) in enumerate(ranked)}

        rrf_scores: Dict[str, float] = {}
        cand_map: Dict[str, MemoryCandidate] = {}
        for cand in first_stage_cands:
            cid = str(cand.get("id", id(cand)))
            cand_map[cid] = cand
            rrf = 0.0
            for name in signal_ranks:
                r = signal_ranks[name].get(cid, len(first_stage_cands) + 1)
                rrf += 1.0 / (self.k + r)
            rrf_scores[cid] = rrf

        sorted_ids = sorted(rrf_scores.keys(), key=lambda x: rrf_scores[x], reverse=True)
        ranked_cands = [cand_map[i] for i in sorted_ids][:top_k]

        if not return_decompositions:
            return ranked_cands, []

        decomps: List[DMUScoreDecomposition] = []
        q_emb = query_context.get("query_embedding", [])
        for rank_idx, cid in enumerate(sorted_ids[:top_k], start=1):
            cand = cand_map[cid]
            cos = _safe_cosine(q_emb, cand.get("embedding", []))
            decomp = build_decomposition(
                candidate_id=cid,
                cosine_similarity=cos,
                recency_score=float(cand.get("timestamp", 0)),
                salience=float(cand.get("salience", 0.5)),
                retention_decay=float(cand.get("retention_score", 0.8)),
                emotional_weight=float(cand.get("emotional_valence", 0.0)),
                state_match=float(cand.get("state_match", 0.6)),
                trust_level=float(cand.get("trust_level", 0.75)),
                conflict_penalty=0.25 if cand.get("has_conflict") else 0.0,
                final_dmu_score=rrf_scores[cid],
                memory_metadata=cand,
                notes=f"RRF_fusion_k={self.k}",
            )
            decomp.rank = rank_idx
            decomps.append(decomp)

        decomps = compute_pure_semantic_ranks(decomps)
        return ranked_cands, decomps


@dataclass
class TwoStageRanker:
    first_stage_k: int = 30
    second_stage_ranker: Optional[Any] = None

    def rank(
        self,
        candidates: List[MemoryCandidate],
        query_context: QueryContext,
        *,
        query_embedding: Optional[List[float]] = None,
        top_k: int = 5,
        return_decompositions: bool = True,
    ) -> Tuple[List[MemoryCandidate], List[DMUScoreDecomposition]]:
        if not candidates:
            return [], []

        q_emb = query_embedding or query_context.get("query_embedding", [])
        scored = [(_safe_cosine(q_emb, c.get("embedding", [])), c) for c in candidates]
        scored.sort(key=lambda x: x[0], reverse=True)
        stage1_cands = [c for _, c in scored[: self.first_stage_k]]

        if self.second_stage_ranker is not None and hasattr(self.second_stage_ranker, "rank"):
            return self.second_stage_ranker.rank(
                stage1_cands,
                query_context,
                query_embedding=q_emb,
                top_k=top_k,
                return_decompositions=return_decompositions,
            )

        if return_decompositions:
            decomps: List[DMUScoreDecomposition] = []
            for i, (_, c) in enumerate(scored[:top_k], 1):
                decomp = build_decomposition(
                    candidate_id=str(c.get("id", f"mem_{i}")),
                    cosine_similarity=scored[i - 1][0],
                    recency_score=0.0,
                    salience=0.0,
                    retention_decay=0.0,
                    emotional_weight=0.0,
                    state_match=0.0,
                    trust_level=0.0,
                    conflict_penalty=0.0,
                    final_dmu_score=scored[i - 1][0],
                    memory_metadata=c,
                    notes="two_stage_fallback_cosine_only",
                )
                decomp.rank = i
                decomps.append(decomp)
            return [c for _, c in scored[:top_k]], decomps

        return [c for _, c in scored[:top_k]], []


def get_ranker(name: str, **kwargs) -> Any:
    name = name.lower()
    if name in ("guarded", "guarded_weighted", "guarded_dmu"):
        return GuardedWeightedRanker(**kwargs)
    if name in ("rrf", "reciprocal", "reciprocal_rank_fusion"):
        return ReciprocalRankFusionRanker(**kwargs)
    if name in ("two_stage", "two-stage", "pipeline"):
        return TwoStageRanker(**kwargs)
    raise ValueError(f"Unknown ranker: {name}. Available: guarded, rrf, two_stage")


if __name__ == "__main__":
    print("Alternative Ranking Algorithms module loaded.")
    print("Available rankers: GuardedWeightedRanker, ReciprocalRankFusionRanker, TwoStageRanker")
