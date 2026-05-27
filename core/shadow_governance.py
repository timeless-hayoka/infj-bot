"""
shadow_governance.py — PHI // DRIFT Shadow Layer
infj_bot/core/shadow_governance.py

Implements bounded uncertainty management for the Shadow layer.
Shadow is unresolved contradiction under time pressure.
It carries signal but must be governed or it becomes noise.

Architecture:
  Meme  → detects and tracks shadow anomalies
  Pulse → applies decay + enforces accumulation cap + chooses mode
  Nexus → uses adjusted confidence; shadow penalizes but does not veto

Three hard controls:
  1. TTL exponential decay — w(t) = w₀ × exp(-t/τ)
  2. Accumulation cap     — shadow_influence = min(Σwᵢ, MAX_SHADOW_WEIGHT)
  3. Promotion threshold  — anomaly must earn influence through persistence

Shadow Operating Modes (tied to Active Mode):
  SECURITY    — τ=15,  max=0.25, promotion=0.30  (fast cleanse)
  BALANCED    — τ=30,  max=0.35, promotion=0.25  (default)
  CONSERVATIVE— τ=50,  max=0.40, promotion=0.20  (reflective)
"""

import math
import time
from dataclasses import dataclass, field
from typing import Optional


# ── Mode Constants ──────────────────────────────────────────────────────────

SHADOW_MODES = {
    "SECURITY": {
        "tau": 15,
        "max_shadow_weight": 0.25,
        "promotion_threshold": 0.30,
        "consistency_window": 3,
    },
    "BALANCED": {
        "tau": 30,
        "max_shadow_weight": 0.35,
        "promotion_threshold": 0.25,
        "consistency_window": 5,
    },
    "CONSERVATIVE": {
        "tau": 50,
        "max_shadow_weight": 0.40,
        "promotion_threshold": 0.20,
        "consistency_window": 7,
    },
}

# Mode aliases — maps DRIFT chat modes to shadow operating modes
MODE_ALIAS = {
    "bughunter": "SECURITY",
    "engineer":  "SECURITY",
    "companion": "BALANCED",
    "coach":     "BALANCED",
    "critic":    "BALANCED",
    "clarity":   "BALANCED",
    "researcher":"CONSERVATIVE",
    "quiet":     "CONSERVATIVE",
    "drift":     "CONSERVATIVE",
}


# ── Data Structures ─────────────────────────────────────────────────────────

@dataclass
class ShadowAnomaly:
    """A single detected shadow anomaly."""
    anomaly_id: str
    description: str
    initial_weight: float
    detected_at_cycle: int
    weight_history: list = field(default_factory=list)
    promoted: bool = False

    def current_weight(self, current_cycle: int, tau: float) -> float:
        """Compute decayed weight at current cycle."""
        t = current_cycle - self.detected_at_cycle
        return self.initial_weight * math.exp(-t / tau)


@dataclass
class ShadowState:
    """Full shadow state for the current session."""
    anomalies: dict = field(default_factory=dict)  # anomaly_id → ShadowAnomaly
    current_cycle: int = 0
    active_mode: str = "BALANCED"
    shadow_influence: float = 0.0
    promoted_anomalies: list = field(default_factory=list)


# ── Core Functions ──────────────────────────────────────────────────────────

def decay_weight(initial_weight: float, time_elapsed: int, tau: float) -> float:
    """
    Exponential decay for shadow anomaly weight.
    w(t) = w₀ × exp(-t/τ)

    Args:
        initial_weight: weight at detection
        time_elapsed:   cycles since detection
        tau:            decay constant (mode-dependent)

    Returns:
        Decayed weight (approaches 0 asymptotically)
    """
    return initial_weight * math.exp(-time_elapsed / tau)


def compute_shadow_influence(anomalies: dict, current_cycle: int, mode: str) -> float:
    """
    Compute total shadow influence across all active anomalies.
    Applies accumulation cap from the active mode.

    Returns value in [0.0, MAX_SHADOW_WEIGHT]
    """
    cfg = SHADOW_MODES.get(mode, SHADOW_MODES["BALANCED"])
    tau = cfg["tau"]
    max_weight = cfg["max_shadow_weight"]

    total = sum(
        a.current_weight(current_cycle, tau)
        for a in anomalies.values()
    )

    return min(total, max_weight)


def should_promote(anomaly: ShadowAnomaly, current_cycle: int, mode: str) -> bool:
    """
    Determine if a shadow anomaly has earned promotion to influence Logic/Ethos.

    Promotion requires:
      1. Current weight >= promotion_threshold
      2. Anomaly has survived consistency_window cycles
      3. Weight has not collapsed below 10% of initial

    Shadow penalizes confidence. It does NOT get veto power unless Ethos allows.
    """
    cfg = SHADOW_MODES.get(mode, SHADOW_MODES["BALANCED"])
    tau = cfg["tau"]
    threshold = cfg["promotion_threshold"]
    window = cfg["consistency_window"]

    age = current_cycle - anomaly.detected_at_cycle
    if age < window:
        return False

    current_w = anomaly.current_weight(current_cycle, tau)
    if current_w < threshold:
        return False

    # Check it hasn't collapsed — still above 10% of initial
    if current_w < anomaly.initial_weight * 0.1:
        return False

    return True


def adjusted_confidence(base_confidence: float, shadow_influence: float) -> float:
    """
    Apply shadow penalty to Nexus confidence score.

    adjusted_confidence = base_confidence × (1.0 - shadow_influence)

    Shadow whispers doubt. It does not command silence.
    """
    return max(0.0, base_confidence * (1.0 - shadow_influence))


def tick(state: ShadowState, new_anomalies: Optional[list] = None) -> ShadowState:
    """
    Advance shadow state by one cycle.

    1. Increment cycle counter
    2. Add any new anomalies detected by Meme
    3. Recompute influence with decay
    4. Evaluate promotions
    5. Prune dead anomalies (< 1% of initial weight)

    Args:
        state:          current ShadowState
        new_anomalies:  list of (anomaly_id, description, weight) tuples from Meme

    Returns:
        Updated ShadowState
    """
    state.current_cycle += 1
    cfg = SHADOW_MODES.get(state.active_mode, SHADOW_MODES["BALANCED"])
    tau = cfg["tau"]

    # Ingest new anomalies from Meme
    if new_anomalies:
        for anomaly_id, description, weight in new_anomalies:
            if anomaly_id not in state.anomalies:
                state.anomalies[anomaly_id] = ShadowAnomaly(
                    anomaly_id=anomaly_id,
                    description=description,
                    initial_weight=weight,
                    detected_at_cycle=state.current_cycle,
                )

    # Evaluate promotions
    for anomaly in state.anomalies.values():
        if not anomaly.promoted and should_promote(anomaly, state.current_cycle, state.active_mode):
            anomaly.promoted = True
            state.promoted_anomalies.append(anomaly.anomaly_id)

    # Prune dead anomalies (< 1% of initial weight)
    dead = [
        aid for aid, a in state.anomalies.items()
        if a.current_weight(state.current_cycle, tau) < a.initial_weight * 0.01
    ]
    for aid in dead:
        state.anomalies.pop(aid, None)

    # Recompute total influence
    state.shadow_influence = compute_shadow_influence(
        state.anomalies, state.current_cycle, state.active_mode
    )

    return state


def resolve_mode(chat_mode: str) -> str:
    """Map DRIFT chat mode to shadow operating mode."""
    return MODE_ALIAS.get(chat_mode, "BALANCED")


# ── Self-Check ──────────────────────────────────────────────────────────────

def self_check():
    print("=" * 60)
    print("SHADOW GOVERNANCE — SELF-CHECK")
    print("=" * 60)

    state = ShadowState(active_mode="BALANCED")

    # Inject test anomalies
    state = tick(state, new_anomalies=[
        ("avoidance_001", "Task repeatedly accessed but never completed", 0.28),
        ("mirror_bias_002", "Consecutive agreements without challenge", 0.18),
    ])

    print(f"Cycle {state.current_cycle}")
    print(f"Active anomalies: {len(state.anomalies)}")
    print(f"Shadow influence: {state.shadow_influence:.3f}")
    print(f"Max allowed (BALANCED): {SHADOW_MODES['BALANCED']['max_shadow_weight']}")

    # Advance cycles to test decay and promotion
    for _ in range(5):
        state = tick(state)

    print(f"\nAfter 5 more cycles:")
    print(f"Shadow influence: {state.shadow_influence:.3f}")
    print(f"Promoted anomalies: {state.promoted_anomalies}")

    # Test adjusted confidence
    base = 0.85
    adj = adjusted_confidence(base, state.shadow_influence)
    print(f"\nBase confidence: {base:.2f}")
    print(f"Adjusted confidence: {adj:.3f}")

    # Test SECURITY mode (fast cleanse)
    state_sec = ShadowState(active_mode="SECURITY")
    state_sec = tick(state_sec, new_anomalies=[
        ("sec_anomaly_001", "High-noise signal in bughunter mode", 0.22),
    ])
    print(f"\nSECURITY mode influence: {state_sec.shadow_influence:.3f}")
    print(f"SECURITY max: {SHADOW_MODES['SECURITY']['max_shadow_weight']}")

    print("\n[OK] Shadow governance self-check complete.")


if __name__ == "__main__":
    self_check()
