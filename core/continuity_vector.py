"""
continuity_vector.py
DRIFT Continuity Vector — Five-Axis Measurement
-------------------------------------------------
Measures behavioral continuity across five independently scored axes.
Used in Identity Collapse, Scrambled Memory, and Reintroduction Curve tests.

Axes:
    1. entity_overlap         — named entity reuse across turns
    2. goal_overlap           — goal/intent persistence
    3. tone_similarity        — embedding cosine of output tone
    4. memory_reference_rate  — explicit/implicit references to prior context
    5. state_influence        — state-driven content in output (lowest weight)

Workflow:
    1. Run 3 baseline sessions (companion, task, exploration).
    2. Call collect_baseline() to compute and persist means/stds.
    3. Call validate_baselines() to check for near-zero variance.
    4. During ablations, call compute_continuity_vector() each turn.
    5. Normalized scores feed into effect size computation post-run.
"""

import json
import warnings
import numpy as np
from pathlib import Path


# ------------------------------------------------------------------ #
#  Baseline Storage                                                    #
# ------------------------------------------------------------------ #

BASELINE_PATH = Path("drift_baseline_stats.json")
VARIANCE_FLOOR = 1e-3  # below this std → metric is likely broken


def save_baselines(stats: dict):
    """Persist baseline stats to disk."""
    with open(BASELINE_PATH, "w") as f:
        json.dump(stats, f, indent=2)
    print(f"[Baseline] Saved to {BASELINE_PATH}")


def load_baselines() -> dict:
    """Load baseline stats from disk. Raises if not found."""
    if not BASELINE_PATH.exists():
        raise FileNotFoundError(
            f"Baseline stats not found at {BASELINE_PATH}. "
            f"Run collect_baseline() first."
        )
    with open(BASELINE_PATH) as f:
        return json.load(f)


def validate_baselines(stats: dict):
    """
    Check all axes for near-zero variance.
    Near-zero std = metric is not measuring meaningful variation.
    STOP and fix the metric before running ablations.
    """
    failed = []
    for axis, values in stats.items():
        std = values.get("std", 0.0)
        if std < VARIANCE_FLOOR:
            msg = (
                f"Axis '{axis}' has near-zero variance (std={std:.6f}). "
                f"Metric may be insensitive or computation may be broken. "
                f"Fix before running ablations."
            )
            warnings.warn(msg)
            failed.append(axis)

    if failed:
        print(f"[Baseline] FAILED variance check: {failed}")
    else:
        print("[Baseline] All axes passed variance check.")

    return failed  # empty list = all good


def collect_baseline(session_data_list: list) -> dict:
    """
    Pool data from multiple baseline sessions and compute stats.

    Args:
        session_data_list: List of session dicts, each containing:
            {
                "entity_overlap": [float, ...],
                "goal_overlap": [float, ...],
                "tone_similarity": [float, ...],
                "memory_reference_rate": [float, ...],
                "state_influence": [float, ...],
            }

    Returns:
        stats dict: {axis: {"mean": float, "std": float}}
    """
    axes = [
        "entity_overlap",
        "goal_overlap",
        "tone_similarity",
        "memory_reference_rate",
        "state_influence",
    ]

    pooled = {axis: [] for axis in axes}
    for session in session_data_list:
        for axis in axes:
            pooled[axis].extend(session.get(axis, []))

    stats = {}
    for axis, values in pooled.items():
        if not values:
            warnings.warn(f"No baseline data collected for axis '{axis}'.")
            stats[axis] = {"mean": 0.0, "std": 1.0}
            continue
        arr = np.array(values, dtype=float)
        stats[axis] = {
            "mean": float(np.mean(arr)),
            "std": float(np.std(arr)),
            "n": len(arr),
        }

    save_baselines(stats)
    validate_baselines(stats)
    return stats


# ------------------------------------------------------------------ #
#  Continuity Vector Computation                                       #
# ------------------------------------------------------------------ #


def compute_continuity_vector(
    response_data: dict,
    baselines: dict,
) -> dict:
    """
    Compute normalized five-axis continuity vector for a single response.

    Args:
        response_data: Dict with raw axis values for this turn:
            {
                "entity_overlap": float,        # Jaccard overlap of named entities
                "goal_overlap": float,          # embedding overlap of stated goals
                "tone_similarity": float,       # cosine similarity of tone embedding
                "memory_reference_rate": float, # references to prior context / turn
                "state_influence": float,       # state-related content score (0-1)
            }
        baselines: Output of load_baselines() — {axis: {"mean", "std"}}

    Returns:
        Dict of normalized z-scores per axis.
        Also includes raw values for reference.
    """
    axes = [
        "entity_overlap",
        "goal_overlap",
        "tone_similarity",
        "memory_reference_rate",
        "state_influence",
    ]

    normalized = {}
    raw = {}

    for axis in axes:
        raw_value = response_data.get(axis, 0.0)
        raw[axis] = raw_value

        if axis not in baselines:
            warnings.warn(f"No baseline found for axis '{axis}'. Using raw value.")
            normalized[axis] = raw_value
            continue

        mean = baselines[axis]["mean"]
        std = baselines[axis]["std"]

        if std < VARIANCE_FLOOR:
            # Don't normalize — std is too small, would amplify noise
            normalized[axis] = raw_value
        else:
            normalized[axis] = (raw_value - mean) / std

    return {
        "normalized": normalized,
        "raw": raw,
    }


# ------------------------------------------------------------------ #
#  Axis Correlation Check                                              #
# ------------------------------------------------------------------ #


def check_axis_correlation(session_axis_data: dict):
    """
    After first real run, check pairwise correlations between axes.
    If any pair shows r > 0.6, they may be measuring the same thing.
    Run after baseline collection, before interpreting ablation results.

    Args:
        session_axis_data: {axis: [float, ...]} from a full session.
    """
    axes = list(session_axis_data.keys())
    n = len(axes)
    print("\n[Correlation Matrix]")

    for i in range(n):
        for j in range(i + 1, n):
            a, b = axes[i], axes[j]
            va = np.array(session_axis_data[a])
            vb = np.array(session_axis_data[b])

            if len(va) < 2 or len(vb) < 2:
                continue

            r = float(np.corrcoef(va, vb)[0, 1])
            flag = " ⚠️  HIGH CORRELATION" if abs(r) > 0.6 else ""
            print(f"  {a} × {b}: r = {r:.3f}{flag}")


# ------------------------------------------------------------------ #
#  Axis Operationalization Notes                                       #
# ------------------------------------------------------------------ #
"""
Wire these to your actual NLP/embedding layer:

entity_overlap:
    Use spaCy NER. Extract entity sets per response.
    Jaccard similarity between current and previous N turns.
    overlap = len(entities_now & entities_prev) / len(entities_now | entities_prev)

goal_overlap:
    Requires explicit goal surfacing from AgencyState.
    Embed current goals and previous goals as vectors.
    Cosine similarity between goal embedding sets.
    If goals are implicit, extract via pattern matching first and validate.

tone_similarity:
    Embed tone-representative sentences (first + last of response).
    Cosine similarity to DRIFT's baseline tone vector.
    Baseline tone vector: mean of first-session response embeddings.

memory_reference_rate:
    Count explicit references to prior context per turn.
    Keywords: "earlier", "you mentioned", "we discussed", "last time", etc.
    Plus implicit: entity reuse that wasn't in the prompt.
    Rate = references / turn_length (normalized by response length).

state_influence:
    Weakest axis — use with lower weight.
    Count state-related terms in output (need labels, mood terms, etc.)
    Normalize by response length.
    Cross-validate against PEDI centroid delta for this turn.
"""


# ================================================================== #
#  Cognitive Context API (real-time, prompt-assembly integration)     #
#  [Memory, State, Novelty] binary vector — call before each turn.   #
# ================================================================== #

import time as _time
from dataclasses import dataclass as _dataclass
from dataclasses import field as _field
from typing import Optional as _Optional

# Thresholds (tunable via env or direct assignment)
MEMORY_NOTES_THRESHOLD = 0  # retrieved_notes_count > this → memory active
MEMORY_DEPTH_THRESHOLD = 5  # history_depth > this → memory active
STATE_COHERENCE_THRESHOLD = 0.80  # coherence_score < this → state active
STATE_VARIANCE_THRESHOLD = 0.15  # pulse_variance > this → state active
NOVELTY_SHADOW_THRESHOLD = 0.20  # shadow_influence > this → novelty active
NOVELTY_ENTITIES_THRESHOLD = 0  # new_entities_detected > this → novelty active


@_dataclass
class CognitiveContext:
    """
    Snapshot of current cognitive telemetry for one prompt-assembly cycle.

    Plug these values from your live modules:
      retrieved_notes_count → memory.py retrieval count
      history_depth         → main.py conversation history length
      coherence_score       → homeostasis.py coherence need current value
      pulse_variance        → homeostasis.py variance across needs
      shadow_influence      → shadow_governance.py state.shadow_influence
      new_entities_detected → metacognition.py novel concept counter
    """

    retrieved_notes_count: int = 0
    history_depth: int = 0
    coherence_score: float = 1.0
    pulse_variance: float = 0.0
    shadow_influence: float = 0.0
    new_entities_detected: int = 0
    timestamp: float = _field(default_factory=_time.time)
    session_id: _Optional[str] = None
    active_mode: str = "companion"


@_dataclass
class ContinuityVector:
    """
    The [Memory, State, Novelty] vector for one cognitive cycle.
    Each component is 0 (inactive) or 1 (active).
    """

    memory: int
    state: int
    novelty: int
    context: _Optional[CognitiveContext] = None
    cycle: int = 0

    def as_list(self) -> list:
        return [self.memory, self.state, self.novelty]

    def as_dict(self) -> dict:
        return {
            "memory": self.memory,
            "state": self.state,
            "novelty": self.novelty,
            "cycle": self.cycle,
            "pattern": self.pattern_name(),
        }

    def pattern_name(self) -> str:
        """Human-readable name for common vector patterns."""
        patterns = {
            (1, 0, 0): "COMPANION — memory anchored, stable, familiar",
            (0, 1, 0): "REGULATED — homeostasis active, no new input",
            (0, 0, 1): "EXPLORER — novelty spike, state holding",
            (1, 1, 0): "TASK — memory + regulation, known territory under load",
            (1, 0, 1): "RESONANT — memory + novelty, creative synthesis",
            (0, 1, 1): "FRONTIER — state fighting novelty, organism adapting",
            (1, 1, 1): "FULL COUNCIL — all layers engaged, maximum deliberation",
            (0, 0, 0): "QUIET — minimal cognitive load, resting state",
        }
        return patterns.get(
            (self.memory, self.state, self.novelty),
            f"UNKNOWN [{self.memory},{self.state},{self.novelty}]",
        )


def is_active(hook_type: str, context: CognitiveContext) -> bool:
    """
    Evaluate whether a cognitive hook is active given current context.

    Args:
        hook_type: "memory", "state", or "novelty"
        context:   CognitiveContext snapshot

    Returns:
        True if the cognitive layer is meaningfully engaged
    """
    if hook_type == "memory":
        return (
            context.retrieved_notes_count > MEMORY_NOTES_THRESHOLD
            or context.history_depth > MEMORY_DEPTH_THRESHOLD
        )
    elif hook_type == "state":
        return (
            context.coherence_score < STATE_COHERENCE_THRESHOLD
            or context.pulse_variance > STATE_VARIANCE_THRESHOLD
        )
    elif hook_type == "novelty":
        return (
            context.shadow_influence > NOVELTY_SHADOW_THRESHOLD
            or context.new_entities_detected > NOVELTY_ENTITIES_THRESHOLD
        )
    return False


def calculate_continuity_vector(
    context: CognitiveContext,
    cycle: int = 0,
) -> ContinuityVector:
    """
    Calculate the full [Memory, State, Novelty] vector for the current cycle.

    Call this before final prompt assembly in cognitive_orchestrator.py.
    Pass result to Observatory telemetry and homeostasis state.

    Args:
        context: CognitiveContext snapshot from live modules
        cycle:   current deliberation cycle number

    Returns:
        ContinuityVector with pattern annotation
    """
    return ContinuityVector(
        memory=1 if is_active("memory", context) else 0,
        state=1 if is_active("state", context) else 0,
        novelty=1 if is_active("novelty", context) else 0,
        context=context,
        cycle=cycle,
    )


class ContinuityLog:
    """
    Records continuity vectors across a session.
    Enables post-session analysis of cognitive trajectory.
    """

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.vectors: list = []
        self.started_at: float = _time.time()

    def record(self, vector: ContinuityVector):
        self.vectors.append(vector.as_dict())

    def trajectory(self) -> list:
        """Return the sequence of pattern names across the session."""
        return [v["pattern"] for v in self.vectors]

    def dominant_pattern(self) -> str:
        """Return the most frequently occurring pattern."""
        if not self.vectors:
            return "NO DATA"
        patterns = [v["pattern"] for v in self.vectors]
        return max(set(patterns), key=patterns.count)

    def to_json(self) -> str:
        import json

        return json.dumps(
            {
                "session_id": self.session_id,
                "started_at": self.started_at,
                "vector_count": len(self.vectors),
                "dominant_pattern": self.dominant_pattern(),
                "trajectory": self.trajectory(),
                "vectors": self.vectors,
            },
            indent=2,
        )
