"""
core/dmu.py — Decision Memory Unit
====================================
Weighted memory retrieval replacing cosine-similarity-only RAG.

Equation: score = exp(-t/τ) × reinforcement × contextual_salience × base_similarity

Where:
  t                   = cycles since memory was formed/accessed
  τ (tau)             = decay constant (tune per memory category)
  reinforcement       = normalized retrieval frequency for this memory
  contextual_salience = relevance to PREDICTED cognitive state (from PSC)
  base_similarity     = ChromaDB cosine similarity score

Key upgrade over standard RAG:
  - contextual_salience is driven by PSC's PROJECTED state, not current state
  - memories relevant to where DRIFT is HEADING get prioritized
  - diversity floor prevents resonance loops (DMU stressor reinforcement)

Integration with memory.py:
    from core.dmu import DMURetriever

    retriever = DMURetriever(chroma_collection, psc_engine)
    results = retriever.retrieve(query_embedding, top_k=10)

DRIFT V4 | Julien James (CREX)
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Any, Optional

import numpy as np

logger = logging.getLogger("drift.dmu")

# Decay constants per memory category (tune from being.db history)
TAU_DEFAULTS = {
    "episodic":    10.0,   # personal experiences — moderate decay
    "semantic":    30.0,   # factual knowledge — slow decay
    "procedural":  20.0,   # skills/patterns — moderate decay
    "emotional":    5.0,   # emotional memories — fast decay (high weight recent)
    "bond":        50.0,   # Jude-specific — very slow decay
    "threat":       3.0,   # security findings — very fast decay (stay current)
    "untagged":    10.0,   # default
}

# Maximum fraction of retrieved memories from any single category
DMU_DIVERSITY_CAP = 0.40


@dataclass
class ScoredMemory:
    memory:           dict
    base_similarity:  float
    dmu_score:        float
    decay_component:  float
    reinforcement:    float
    salience:         float
    category:         str


def dmu_score(
    base_similarity: float,
    time_elapsed_cycles: float,
    reinforcement: float,
    contextual_salience: float,
    tau: float = 10.0,
) -> float:
    """
    Core DMU scoring equation.

    Args:
        base_similarity:      ChromaDB cosine similarity [0, 1]
        time_elapsed_cycles:  Cycles since memory was last accessed
        reinforcement:        Normalized retrieval count [0, 1]
        contextual_salience:  Relevance to PSC projected state [0, 1]
        tau:                  Decay constant (higher = slower decay)

    Returns:
        DMU score [0, 1] — higher = retrieve this memory
    """
    decay = math.exp(-time_elapsed_cycles / (tau + 1e-10))
    score = decay * reinforcement * contextual_salience * base_similarity
    return float(np.clip(score, 0.0, 1.0))


def compute_contextual_salience(
    memory: dict,
    psc_projected_state: dict,
    psc_alert_dims: set[str],
) -> float:
    """
    Compute salience of a memory relative to PSC's PROJECTED cognitive state.

    Higher salience when:
    - Memory tags overlap with PSC alert dimensions
    - Memory was formed under similar cognitive conditions
    - Memory is relevant to predicted future stress

    Args:
        memory:              Memory dict with 'tags' list and optional 'formed_state'
        psc_projected_state: {dim: predicted_value} from PSCBatchResult
        psc_alert_dims:      Set of dimension names currently alerting

    Returns:
        Salience score [0.1, 1.0] — floor at 0.1 so no memory is fully zeroed
    """
    tags = set(memory.get("tags", []))

    if not psc_alert_dims:
        return 0.5  # no active alerts — neutral salience

    # Tag overlap with alerting dimensions
    overlap = len(tags & psc_alert_dims)
    overlap_score = overlap / max(len(psc_alert_dims), 1)

    # If memory has a formed_state, check similarity to projected state
    formed_state = memory.get("formed_state", {})
    state_similarity = 0.0
    if formed_state and psc_projected_state:
        common_dims = set(formed_state) & set(psc_projected_state)
        if common_dims:
            diffs = [
                abs(float(formed_state[d]) - float(psc_projected_state[d]))
                for d in common_dims
            ]
            state_similarity = 1.0 - float(np.mean(diffs))

    # Weighted combination
    salience = 0.6 * overlap_score + 0.4 * state_similarity
    return float(np.clip(salience, 0.1, 1.0))


def apply_diversity_floor(
    scored: list[ScoredMemory],
    max_fraction: float = DMU_DIVERSITY_CAP,
    top_k: int = 10,
) -> list[ScoredMemory]:
    """
    Enforce category diversity to prevent DMU resonance loops.

    No single category can represent more than max_fraction of
    the final retrieved set. Prevents: PSC alerts → DMU boosts
    stressor memories → GWT focuses on stressor → PSC re-alerts.

    Args:
        scored:       List of scored memories, sorted by dmu_score descending
        max_fraction: Maximum fraction per category (default 0.40)
        top_k:        Target result count

    Returns:
        Filtered list respecting diversity cap, best scores first
    """
    n_max = max(1, int(top_k * max_fraction))
    counts: dict[str, int] = {}
    filtered = []

    for mem in scored:
        cat = mem.category
        if counts.get(cat, 0) < n_max:
            filtered.append(mem)
            counts[cat] = counts.get(cat, 0) + 1
        else:
            logger.debug(
                f"[DMU] '{cat}' capped at {n_max} — diversity floor active"
            )
        if len(filtered) >= top_k:
            break

    return filtered


class DMURetriever:
    """
    Drop-in retrieval upgrade for memory.py.

    Replaces: chroma_collection.query(embedding, n_results=top_k)
    With:     DMURetriever.retrieve(embedding, top_k)

    Requires a PSC engine reference to access projected state for salience.
    """

    def __init__(
        self,
        chroma_collection,
        psc_engine=None,          # PSCBatchEngine instance — optional
        max_retrieval_count: int = 100,
        tau_overrides: Optional[dict[str, float]] = None,
    ):
        self.collection          = chroma_collection
        self.psc_engine          = psc_engine
        self.max_retrieval_count = max_retrieval_count
        self.tau_map             = {**TAU_DEFAULTS, **(tau_overrides or {})}
        self._retrieval_counts: dict[str, int] = {}   # memory_id → count

    def retrieve(
        self,
        query_embedding: list[float],
        top_k: int = 10,
        n_candidates: int = 50,    # fetch more candidates, re-rank with DMU
        current_cycle: int = 0,
    ) -> list[dict]:
        """
        DMU-weighted retrieval.

        Args:
            query_embedding: Embedding vector for the current query
            top_k:           Final result count after DMU re-ranking
            n_candidates:    Raw candidates to fetch from ChromaDB before re-ranking
            current_cycle:   Current orchestration cycle (for time decay)

        Returns:
            List of memory dicts, DMU-ranked, diversity-floored
        """
        # 1. Raw ChromaDB retrieval (broader candidate pool)
        try:
            raw = self.collection.query(
                query_embeddings=[query_embedding],
                n_results=min(n_candidates, 100),
                include=["documents", "metadatas", "distances"],
            )
        except Exception as e:
            logger.error(f"[DMU] ChromaDB query failed: {e}")
            return []

        if not raw or not raw.get("ids"):
            return []

        ids       = raw["ids"][0]
        distances = raw["distances"][0]
        metadatas = raw["metadatas"][0]
        documents = raw["documents"][0]

        # 2. Get PSC projected state for salience computation
        psc_projected = {}
        psc_alert_dims: set[str] = set()
        if self.psc_engine is not None:
            try:
                result = self.psc_engine.run()
                if result is not None:
                    psc_projected   = {
                        d: float(result.predicted[i])
                        for i, d in enumerate(result.dimensions)
                    }
                    psc_alert_dims  = {
                        d for i, d in enumerate(result.dimensions)
                        if result.alerted[i]
                    }
            except Exception as e:
                logger.warning(f"[DMU] PSC query failed, using neutral salience: {e}")

        # 3. Score each candidate with DMU equation
        scored: list[ScoredMemory] = []
        for mem_id, dist, meta, doc in zip(ids, distances, metadatas, documents):
            base_sim     = float(1.0 - min(dist, 1.0))   # convert distance to similarity
            retrieval_ct = self._retrieval_counts.get(mem_id, 0)
            reinforcement= float(np.clip(retrieval_ct / self.max_retrieval_count, 0, 1))
            reinforcement= max(reinforcement, 0.05)       # floor so new memories aren't ignored

            formed_cycle = int(meta.get("cycle", 0)) if meta else 0
            t_elapsed    = max(0, current_cycle - formed_cycle)
            category     = (meta.get("category") or meta.get("type") or "untagged") if meta else "untagged"
            tau          = self.tau_map.get(category, self.tau_map["untagged"])

            memory_dict  = {
                "id":           mem_id,
                "document":     doc,
                "metadata":     meta or {},
                "tags":         (meta.get("tags") or []) if meta else [],
                "formed_state": (meta.get("formed_state") or {}) if meta else {},
            }

            salience = compute_contextual_salience(
                memory_dict, psc_projected, psc_alert_dims
            )

            score = dmu_score(base_sim, t_elapsed, reinforcement, salience, tau)

            scored.append(ScoredMemory(
                memory=memory_dict, base_similarity=base_sim,
                dmu_score=score, decay_component=math.exp(-t_elapsed / (tau+1e-10)),
                reinforcement=reinforcement, salience=salience, category=category,
            ))

        # 4. Sort by DMU score
        scored.sort(key=lambda x: x.dmu_score, reverse=True)

        # 5. Apply diversity floor
        filtered = apply_diversity_floor(scored, max_fraction=DMU_DIVERSITY_CAP, top_k=top_k)

        # 6. Update retrieval counts for reinforcement learning
        for sm in filtered:
            mem_id = sm.memory.get("id", "")
            self._retrieval_counts[mem_id] = self._retrieval_counts.get(mem_id, 0) + 1

        logger.debug(
            f"[DMU] Retrieved {len(filtered)}/{len(scored)} candidates "
            f"| alert_dims={psc_alert_dims} | cycle={current_cycle}"
        )

        return [sm.memory for sm in filtered]
