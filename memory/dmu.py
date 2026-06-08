"""DMU Engine — Dynamic Memory Unit.

The DMU ranks retrieved memories not merely by semantic similarity, but by a
composite **Memory Persistence Score (MPS)** that models how human-like recall
actually works: strong emotions anchor memories, time erodes them, and recent
events compete for attention.

Mathematical Model
------------------
1. TIME DECAY — Exponential Forgetting Curve
   The raw retention of a memory at age t (seconds since creation) follows
   the Ebbinghaus exponential decay:

       R(t) = e^( -λ * t )

   where λ (lambda) is the base decay constant. By default λ = 1.0 / HALF_LIFE
   so that R(t) = 0.5 when t == HALF_LIFE seconds.

   However, emotional weight E ∈ [0, 1] **modulates** the effective decay rate.
   High-emotion memories fade more slowly. We model this as a dampened decay
   coefficient:

       λ_eff = λ_base / ( 1 + α * E )

   where α (alpha) is the EMOTIONAL_DAMPING factor. When E = 1 and α = 2,
   the effective half-life triples — the memory persists three times longer.

   Therefore the **emotionally-weighted retention curve** is:

       R(t, E) = e^( -λ_base * t / (1 + α * E) )

2. COMPOSITE MEMORY PERSISTENCE SCORE (MPS)
   For each candidate memory we compute a scalar score in [0, 1]:

       MPS = w_sim * S + w_time * R(t, E) + w_emo * E + w_rec * recency_bonus

   where:
       S  = semantic similarity to the query (from vector search, already in [0,1])
       R  = time-decay retention explained above
       E  = emotional weight stored in memory metadata
       recency_bonus = 1.0 if t < RECENCY_WINDOW else 0.0

   The weights sum to 1.0 so that MPS is interpretable as a probability-like
   relevance measure.

3. RETRIEVAL PIPELINE
   Step A: Vector search returns top-K candidates by semantic similarity.
   Step B: DMU re-ranks those candidates by MPS.
   Step C: The final context window receives memories sorted by MPS descending.

This architecture deliberately separates "what is semantically related" from
"what is psychologically salient" — mirroring how an INFJ cognitive style
prioritizes emotionally significant patterns over purely logical association.
"""

import math
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from infj_bot.core.config import DATA_DIR

DMU_DB = DATA_DIR / "dmu.db"

# ── Decay Constants ──────────────────────────────────────────────────
# HALF_LIFE: seconds after which an emotionally-neutral memory loses 50%
# of its retrieval strength. Default ~24 hours.
HALF_LIFE_SECONDS: float = 86_400.0

# λ_base derived from half-life: R(t) = e^(-λt) → 0.5 = e^(-λ * HALF_LIFE)
# → λ = ln(2) / HALF_LIFE
_LAMBDA_BASE: float = math.log(2) / HALF_LIFE_SECONDS

# EMOTIONAL_DAMPING (α): scales how much emotional weight slows decay.
# α = 2.0 means a fully emotional memory (E=1) decays at 1/3 the normal rate.
EMOTIONAL_DAMPING: float = 2.0

# RECENCY_WINDOW: seconds within which a memory gets a hard recency boost.
RECENCY_WINDOW_SECONDS: float = 3_600.0  # 1 hour

# MPS composite weights — must sum to 1.0
WEIGHTS: Dict[str, float] = {
    "semantic": 0.255,
    "temporal": 0.2975,
    "emotional": 0.2125,
    "recency": 0.085,
    "source_reliability": 0.15,
}
assert abs(sum(WEIGHTS.values()) - 1.0) < 1e-9, "MPS weights must sum to 1.0"

PROVENANCE_SCORES: Dict[str, float] = {
    "user_explicit": 1.0,
    "bot_inference": 0.6,
    "conflicting_block": 0.2,
    "corrupted_block": 0.1,
}


@dataclass
class MemoryCandidate:
    """A memory retrieved from vector search, ready for DMU re-ranking."""

    memory_id: str
    text: str
    created_at: datetime
    semantic_score: float  # from vector similarity, already normalized ~[0,1]
    emotional_weight: float  # E ∈ [0, 1], stored in memory metadata
    source: str = "unknown"
    provenance: str = "user_explicit"
    source_reliability: float = 1.0



class DynamicMemoryUnit:
    """Ranks memories by psychological salience using time-decay + emotion."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = str(db_path or DMU_DB)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        """SQLite backing store for audit trails and tuning telemetry."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS dmu_rankings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    query TEXT,
                    memory_id TEXT NOT NULL,
                    semantic_score REAL,
                    retention_score REAL,
                    emotional_weight REAL,
                    recency_bonus REAL,
                    source_reliability REAL DEFAULT 1.0,
                    provenance TEXT DEFAULT 'user_explicit',
                    mps REAL NOT NULL
                )
            """)
            try:
                conn.execute("ALTER TABLE dmu_rankings ADD COLUMN source_reliability REAL DEFAULT 1.0")
            except sqlite3.OperationalError:
                pass
            try:
                conn.execute("ALTER TABLE dmu_rankings ADD COLUMN provenance TEXT DEFAULT 'user_explicit'")
            except sqlite3.OperationalError:
                pass
            conn.commit()

    # ── Core Mathematics ───────────────────────────────────────────────

    @staticmethod
    def _retention_curve(age_seconds: float, emotional_weight: float) -> float:
        """
        Compute the emotionally-weighted retention score R(t, E).

        Formula:
            λ_eff = λ_base / (1 + α * E)
            R(t, E) = e^( -λ_eff * t )

        Parameters
        ----------
        age_seconds : float
            Time since memory creation (t ≥ 0).
        emotional_weight : float
            Emotional salience E ∈ [0, 1]. Higher E → slower decay.

        Returns
        -------
        float
            Retention strength in [0, 1]. 1.0 = perfectly fresh, 0.0 = fully faded.
        """
        if age_seconds < 0:
            age_seconds = 0.0

        # Dampen decay rate proportionally to emotional weight.
        # Example: E=0 → λ_eff = λ_base (normal forgetting)
        #          E=1, α=2 → λ_eff = λ_base / 3.0 (three times slower forgetting)
        lambda_eff = _LAMBDA_BASE / (1.0 + EMOTIONAL_DAMPING * emotional_weight)

        # Exponential decay: as t → ∞, R → 0; as t → 0, R → 1.
        retention = math.exp(-lambda_eff * age_seconds)
        return retention

    @staticmethod
    def _recency_bonus(age_seconds: float) -> float:
        """
        Hard recency boost for very fresh memories.

        Returns 1.0 if age < RECENCY_WINDOW_SECONDS, else 0.0.
        This models the cognitive "availability heuristic" — recent events
        are disproportionately accessible regardless of semantic or emotional
        content.
        """
        return 1.0 if age_seconds < RECENCY_WINDOW_SECONDS else 0.0

    def compute_mps(
        self, candidate: MemoryCandidate, now: Optional[datetime] = None, query: str = ""
    ) -> float:
        """
        Compute the Composite Memory Persistence Score (MPS) for a candidate.

        Formula:
            MPS = w_sim * S + w_time * R(t, E) + w_emo * E + w_rec * recency + w_rel * reliability_term

        Each term is bounded in [0, 1], and weights sum to 1.0, so MPS ∈ [0, 1].

        Parameters
        ----------
        candidate : MemoryCandidate
            The memory to score.
        now : datetime, optional
            Reference time for age calculation. Defaults to UTC now.

        Returns
        -------
        float
            Composite persistence score in [0, 1]. Higher = more salient.
        """
        if now is None:
            now = datetime.now(timezone.utc)

        # Guard against naive datetimes
        created = candidate.created_at
        if created.tzinfo is None:
            created = created.replace(timezone.utc)

        age_seconds = (now - created).total_seconds()

        # Term 1: Semantic similarity with sparse keyword overlap boost
        boost = 0.0
        if query:
            try:
                import re
                query_words = set(re.findall(r"\b\w{3,}\b", query.lower()))
                content_words = set(re.findall(r"\b\w{3,}\b", candidate.text.lower()))
                overlap = query_words.intersection(content_words)
                if query_words:
                    boost = 0.2 * (len(overlap) / len(query_words))
            except Exception:
                pass
        S = max(0.0, min(1.0, candidate.semantic_score + boost))

        # Term 2: Time-decay retention with emotional modulation
        R = self._retention_curve(age_seconds, candidate.emotional_weight)

        # Term 3: Emotional weight (direct linear contribution)
        E = max(0.0, min(1.0, candidate.emotional_weight))

        # Term 4: Recency availability heuristic
        recency = self._recency_bonus(age_seconds)

        # Term 5: Source Reliability
        prov_score = PROVENANCE_SCORES.get(candidate.provenance, 0.5)
        reliability_term = prov_score * candidate.source_reliability

        # Weighted sum
        mps = (
            WEIGHTS["semantic"] * S
            + WEIGHTS["temporal"] * R
            + WEIGHTS["emotional"] * E
            + WEIGHTS["recency"] * recency
            + WEIGHTS["source_reliability"] * reliability_term
        )

        return round(max(0.0, min(1.0, mps)), 6)

    # ── Ranking API ────────────────────────────────────────────────────

    def rank_memories(
        self,
        candidates: List[MemoryCandidate],
        query: str = "",
        top_k: int = 10,
        now: Optional[datetime] = None,
    ) -> List[Tuple[MemoryCandidate, float]]:
        """
        Re-rank a list of memory candidates by MPS and return top-k.

        Also logs the ranking telemetry to SQLite for later analysis.
        """
        if now is None:
            now = datetime.now(timezone.utc)

        scored = []
        for cand in candidates:
            mps = self.compute_mps(cand, now=now, query=query)
            scored.append((cand, mps))
            self._log_ranking(query, cand, mps, now)

        # Sort descending by MPS
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]

    def _log_ranking(
        self,
        query: str,
        cand: MemoryCandidate,
        mps: float,
        now: datetime,
    ) -> None:
        """Persist scoring breakdown for audit and tuning."""
        age_seconds = (
            (now - cand.created_at).total_seconds() if cand.created_at else 0.0
        )
        retention = self._retention_curve(age_seconds, cand.emotional_weight)
        recency = self._recency_bonus(age_seconds)

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO dmu_rankings
                (timestamp, query, memory_id, semantic_score, retention_score,
                 emotional_weight, recency_bonus, source_reliability, provenance, mps)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now.isoformat(),
                    query,
                    cand.memory_id,
                    cand.semantic_score,
                    retention,
                    cand.emotional_weight,
                    recency,
                    cand.source_reliability,
                    cand.provenance,
                    mps,
                ),
            )
            conn.commit()

    # ── Telemetry ──────────────────────────────────────────────────────

    def get_ranking_history(self, limit: int = 100) -> List[Dict]:
        """Return recent DMU ranking records for debugging / audit."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM dmu_rankings ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]


# ── Integration helpers ──────────────────────────────────────────────


def rank_memory_entries(
    entries,
    query: str = "",
    top_k: int = 10,
    now: Optional[datetime] = None,
) -> List[Tuple[MemoryCandidate, float]]:
    """
    Adapter that bridges the Unified Memory Spine (MemoryEntry) with the DMU.

    The Unified Memory Spine already computes an internal DMU score in
    `MemoryManager._calculate_dmu()`. This function takes the raw MemoryEntry
    objects returned by `recall_sync()`, converts them into MemoryCandidates
    using the *original semantic similarity* approximated from the stored score,
    and applies the DMU re-ranking layer defined above.

    Parameters
    ----------
    entries : List[MemoryEntry]
        Results from `MemoryManager.recall_sync()`.
    query : str
        The original user query (used for telemetry only).
    top_k : int
        How many entries to return after re-ranking.
    now : datetime, optional
        Reference time for age calculation.

    Returns
    -------
    List[Tuple[MemoryCandidate, float]]
        Entries re-ranked by DMU Memory Persistence Score (MPS).
    """
    candidates = []
    for entry in entries:
        # The unified spine stores the final blended score in entry.score.
        # We approximate the raw semantic component by backing out the
        # time-decay factor. This is imperfect but sufficient for telemetry.
        ts = entry.event.timestamp
        (now or datetime.now(timezone.utc) - ts).total_seconds()
        emotional = float(
            entry.metadata.get(
                "emotion_intensity", entry.metadata.get("emotional", 0.5)
            )
        )
        provenance = entry.metadata.get("provenance", "user_explicit")
        source_reliability = float(entry.metadata.get("source_reliability", 1.0))
        # Approximate raw semantic score from the unified DMU (upper bound)
        approx_semantic = min(1.0, entry.score * 1.2)

        cand = MemoryCandidate(
            memory_id=entry.unified_id,
            text=entry.event.content,
            created_at=ts,
            semantic_score=approx_semantic,
            emotional_weight=emotional,
            source=entry.metadata.get("type", "unknown"),
            provenance=provenance,
            source_reliability=source_reliability,
        )
        candidates.append(cand)

    dmu = get_dmu()
    return dmu.rank_memories(candidates, query=query, top_k=top_k, now=now)


def format_ranked_entries(ranked: List[Tuple[MemoryCandidate, float]]) -> str:
    """Convert DMU-ranked entries into the string format expected by the prompt builder."""
    # Chronological Prompt Sorting: sort selected memories chronologically ascending (oldest first)
    chronological = sorted(ranked, key=lambda x: x[0].created_at)
    
    lines = []
    for cand, mps in chronological:
        lines.append(f"[{cand.source}] [provenance: {cand.provenance}] (salience: {mps:.2f})\n{cand.text}")
    return "\n---\n".join(lines)


# ── Convenience factory ──────────────────────────────────────────────

_default_dmu: Optional[DynamicMemoryUnit] = None


def get_dmu() -> DynamicMemoryUnit:
    """Return the singleton DynamicMemoryUnit instance."""
    global _default_dmu
    if _default_dmu is None:
        _default_dmu = DynamicMemoryUnit()
    return _default_dmu
