"""
dmu_scoring.py
DRIFT DMU — Memory Prioritization Scoring (MPS)
-------------------------------------------------
Fully additive scoring regime replacing the original multiplicative formula.
Weights are externalized to MPS_WEIGHTS dict — tune from config, not here.
score_components is explicitly set on every memory object for logging.

Integration:
    - Import compute_mps into your DMU/memory retrieval module.
    - Pass experiment_control instance in or access via singleton.
    - Call after candidate retrieval (top 30-50 from ChromaDB).
    - Re-rank candidates by returned score, select top K.
"""

import math
import time

# ------------------------------------------------------------------ #
#  Weight Config                                                       #
#  Move to config.py or your main config module.                      #
#  These are UNVALIDATED starting points — run sensitivity analysis   #
#  after first ablation suite to tune.                                #
#  Verify all factors span comparable [0,1] ranges before weighting.  #
# ------------------------------------------------------------------ #

MPS_WEIGHTS = {
    "decay":        0.25,
    "reinf":        0.20,
    "contextual":   0.20,
    "recency_bias": 0.15,
    "novelty":      0.10,
    "state_align":  0.10,
}

# Gamma for decay shaping.
# gamma < 1.0 boosts high-retention memories (e.g. 0.5 = strong boost)
# gamma = 1.0 = no shaping (original)
# gamma > 1.0 = punishes older memories harder
DECAY_GAMMA = 0.5

# Recency window and time constant (in turns)
RECENCY_K = 10          # how many recent memory uses to track
RECENCY_TAU = 20.0      # half-life in turns for recency weight decay

# Novelty similarity threshold — novelty only boosts within relevant context
NOVELTY_SIM_THRESHOLD = 0.4

# Session tau for decay (seconds). Default 24h.
DEFAULT_TAU = 86400


def compute_mps(
    memory,
    current_state: dict,
    current_mode: str = "relational",
    recent_memory_usage: list = None,     # list of (memory_id, turn_delta) tuples
    experiment_control=None,
    tau: float = DEFAULT_TAU,
) -> float:
    """
    Compute Memory Prioritization Score for a single memory candidate.

    Args:
        memory:               Memory object with .timestamp, .reinforcement_score,
                              .novelty_score, .id, .extra_flags attributes.
        current_state:        Dict of current homeostasis/cognitive state values.
        current_mode:         "relational" | "task" | "exploration"
        recent_memory_usage:  Last K (memory_id, turn_delta) pairs for recency bias.
        experiment_control:   ExperimentControl instance for freeze checks.
        tau:                  Decay time constant in seconds.

    Returns:
        float in [0.0, 1.0] — higher = higher retrieval priority.
        Also sets memory.score_components dict for logging.
    """

    # ---- Decay (gamma-shaped) ---- #
    t = time.time() - memory.timestamp
    raw_decay = math.exp(-t / tau)
    decay = raw_decay ** DECAY_GAMMA  # shape the upper range

    # ---- Reinforcement (sub-linear) ---- #
    reinf = min(memory.reinforcement_score ** 0.75, 1.0)

    # ---- Contextual similarity ---- #
    # Replace with your actual embedding/keyword similarity function.
    contextual = _normalized_contextual_sim(memory, current_state)

    # ---- Decaying recency bias ---- #
    recency_bias = _get_decaying_recency_weight(memory.id, recent_memory_usage or [])

    # ---- Mode-aware, context-gated novelty ---- #
    novelty_raw = getattr(memory, 'novelty_score', 0.0)

    # Gate: novelty only boosts if contextual similarity is above threshold
    # (prevents pulling irrelevant-but-novel memories)
    if contextual >= NOVELTY_SIM_THRESHOLD:
        novelty_gated = novelty_raw
        if current_mode == "task":
            novelty_gated *= 0.5
        elif current_mode == "exploration":
            novelty_gated *= 1.3
    else:
        novelty_gated = 0.0

    # Freeze check — set to additive neutral (0.0) when frozen
    if experiment_control and not experiment_control.is_active("novelty"):
        novelty_gated = 0.0

    # ---- State alignment ---- #
    state_align = _state_alignment_score(memory, current_state)

    # ---- Additive MPS ---- #
    mps = (
        MPS_WEIGHTS["decay"]        * decay        +
        MPS_WEIGHTS["reinf"]        * reinf        +
        MPS_WEIGHTS["contextual"]   * contextual   +
        MPS_WEIGHTS["recency_bias"] * recency_bias +
        MPS_WEIGHTS["novelty"]      * novelty_gated +
        MPS_WEIGHTS["state_align"]  * state_align
    )
    mps = max(0.0, min(1.0, mps))

    # ---- Attach components for logging (always, even if 0) ---- #
    memory.score_components = {
        "decay":         decay,
        "reinf":         reinf,
        "contextual":    contextual,
        "recency_bias":  recency_bias,
        "novelty":       novelty_gated,
        "state_align":   state_align,
        "final_mps":     mps,
        "mode":          current_mode,
    }

    return mps


# ------------------------------------------------------------------ #
#  Helper Functions                                                    #
#  Replace stubs with your actual implementations.                    #
# ------------------------------------------------------------------ #

def _get_decaying_recency_weight(memory_id: str, last_k_used: list) -> float:
    """
    Weighted recency bias with exponential decay over turns.
    Prevents sticky-memory: recently used but now less relevant memories
    fade naturally rather than staying dominant.

    last_k_used: list of (memory_id, turn_delta) tuples, most recent first.
    turn_delta: how many turns ago this memory was used.
    """
    weight = sum(
        (1.0 / rank) * math.exp(-turn_delta / RECENCY_TAU)
        for rank, (mid, turn_delta) in enumerate(last_k_used[:RECENCY_K], 1)
        if mid == memory_id
    )
    return min(weight * 0.4, 1.0)  # cap influence at 1.0


def _normalized_contextual_sim(memory, current_state: dict) -> float:
    """
    Compute contextual similarity between memory content and current state.
    Uses LocalEmbeddingFunction for deterministic hash-based similarity.
    Returns float in [0.0, 1.0].
    """
    from infj_bot.core.embeddings import LocalEmbeddingFunction
    emb = LocalEmbeddingFunction()
    mem_vec = emb.embed_query(getattr(memory, 'content', str(memory)))
    state_vec = emb.embed_query(str(current_state))
    # Cosine similarity
    dot = sum(a * b for a, b in zip(mem_vec, state_vec))
    mag_a = sum(a * a for a in mem_vec) ** 0.5
    mag_b = sum(b * b for b in state_vec) ** 0.5
    if mag_a == 0 or mag_b == 0:
        return 0.0
    sim = dot / (mag_a * mag_b)
    # Normalize [-1, 1] → [0, 1]
    return (sim + 1.0) / 2.0


def _state_alignment_score(memory, current_state: dict) -> float:
    """
    Compute how relevant this memory is to current need-state deficits.
    Simple heuristic: if memory tags overlap with current_state keys, higher alignment.
    Returns float in [0.0, 1.0].
    """
    mem_tags = set(getattr(memory, 'tags', []) or [])
    state_keys = set(current_state.keys())
    if not mem_tags or not state_keys:
        return 0.5
    overlap = len(mem_tags & state_keys)
    union = len(mem_tags | state_keys)
    return overlap / union if union > 0 else 0.0


# ------------------------------------------------------------------ #
#  Two-Stage Retrieval Wrapper                                         #
# ------------------------------------------------------------------ #

def retrieve_and_rank(
    query_state: dict,
    chromadb_collection,
    experiment_control=None,
    current_mode: str = "relational",
    recent_memory_usage: list = None,
    wide_k: int = 40,
    final_k: int = 10,
) -> tuple:
    """
    Two-stage retrieval:
      1. Wide vector pull from ChromaDB (fast approximate nearest-neighbor)
      2. DMU rerank using full additive MPS

    Returns:
        (selected, rejected_top5)
        Each is a list of memory objects with .score and .score_components set.
    """
    # Stage 1: wide pull
    candidates_raw = chromadb_collection.query(
        query_texts=[str(query_state)],
        n_results=wide_k
    )
    # Convert ChromaDB results to your memory objects here.
    # This is a stub — wire to your actual memory object factory.
    candidates = _chromadb_results_to_memories(candidates_raw)

    # Hard gate before scoring: skip obviously irrelevant memories
    candidates = [
        m for m in candidates
        if not _is_hard_gated(m)
    ]

    # Stage 2: DMU rerank
    for memory in candidates:
        memory.score = compute_mps(
            memory=memory,
            current_state=query_state,
            current_mode=current_mode,
            recent_memory_usage=recent_memory_usage,
            experiment_control=experiment_control,
        )

    candidates.sort(key=lambda m: m.score, reverse=True)

    selected = candidates[:final_k]
    rejected_top5 = candidates[final_k:final_k + 5]

    return selected, rejected_top5


def _is_hard_gated(memory) -> bool:
    """
    Hard gate: filter obviously irrelevant memories before scoring.
    Cuts compute on clear misses.
    """
    MAX_AGE_SECONDS = 30 * 24 * 3600  # 30 days
    MIN_REINFORCEMENT = 0.2

    age = time.time() - memory.timestamp
    if age > MAX_AGE_SECONDS and memory.reinforcement_score < MIN_REINFORCEMENT:
        return True  # gate out
    return False


class _DMUMemory:
    """Lightweight memory adapter for DMU scoring."""
    def __init__(self, content: str, memory_id: str = "", timestamp: float = 0.0,
                 reinforcement_score: float = 0.5, novelty_score: float = 0.5,
                 tags: list = None, extra_flags: dict = None):
        self.content = content
        self.id = memory_id or str(hash(content))[:8]
        self.timestamp = timestamp
        self.reinforcement_score = reinforcement_score
        self.novelty_score = novelty_score
        self.tags = tags or []
        self.extra_flags = extra_flags or {}
        self.score = 0.0
        self.score_components = {}


def _chromadb_results_to_memories(chromadb_results):
    """
    Convert ChromaDB query results to DMU memory objects.
    """
    memories = []
    docs = chromadb_results.get("documents", [[]])[0] if chromadb_results else []
    metas = chromadb_results.get("metadatas", [[]])[0] if chromadb_results else []
    ids = chromadb_results.get("ids", [[]])[0] if chromadb_results else []
    for i, doc in enumerate(docs):
        meta = metas[i] if i < len(metas) else {}
        mem_id = ids[i] if i < len(ids) else str(hash(doc))[:8]
        ts = meta.get("timestamp", 0.0)
        if isinstance(ts, str):
            try:
                from datetime import datetime
                ts = datetime.fromisoformat(ts).timestamp()
            except Exception:
                ts = 0.0
        memories.append(_DMUMemory(
            content=doc,
            memory_id=mem_id,
            timestamp=ts,
            reinforcement_score=meta.get("reinforcement_score", 0.5),
            novelty_score=meta.get("novelty_score", 0.5),
            tags=meta.get("tags", []),
        ))
    return memories
