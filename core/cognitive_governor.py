"""
core/cognitive_governor.py — Energy-coupled behavior control for DRIFT.

WHAT THIS DOES
    Converts energy from a passive telemetry metric into an active behavioral
    constraint. Every metric must answer "what action does this trigger?" —
    if it doesn't change behavior, it's emotional support logging.

WHAT THIS DOES NOT DO (yet — prerequisites missing)
    - Temperature gating via fatigue: unvalidated mechanism. Test in isolation
      before using as a control lever. Temperature → output quality is not
      a reliable causal chain at Gemini's scale.
    - DII gating: DII is currently a constant (tracker not initialized).
      Enable after DII tracker is live and shows variance.
    - Coherence gating: 0/15 populated in current trajectory logs.
      Enable after coherence sensor is confirmed working.

INTEGRATION POINTS
    In brain.py agent_turn, BEFORE the inference call:
        from core.cognitive_governor import CognitiveGovernor
        # module-level: _governor = CognitiveGovernor()
        gate_result = _governor.apply(being.state.energy, turn=self.turns)
        # pass gate_result.max_tokens to the generation call
        # pass gate_result.interventions to log_turn metadata

    In homeostasis.py update_needs, AFTER updating energy:
        _governor.record_turn(
            prev_energy=prev_e,
            new_energy=being.state.energy,
            response_len=timing.get("response_len", 0) if timing else 0,
            gate_result=last_gate_result,  # stored on brain between calls
        )
"""

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

import numpy as np


# --------------------------------------------------------------------------- #
# Mode definitions — integrate with existing DRIFT mode names
# Energy modes MODIFY the current mode's parameters, not replace it
# --------------------------------------------------------------------------- #
ENERGY_MODES = {
    "NORMAL": {
        "max_tokens": 1000,
        "description": "Full cognitive capacity",
    },
    "LOW_POWER": {
        "max_tokens": 400,
        "description": "Conserving — longer responses deferred",
    },
    "CRITICAL": {
        "max_tokens": 150,
        "description": "Minimal output — system recovering",
    },
    "HOLD": {
        "max_tokens": 80,
        "description": "Sensor invalid — respond but do not act on state",
    },
}

ENERGY_THRESHOLDS = {
    "NORMAL":    (0.30, 1.00),   # energy >= 0.30
    "LOW_POWER": (0.15, 0.30),   # 0.15 <= energy < 0.30
    "CRITICAL":  (0.00, 0.15),   # energy < 0.15
}


@dataclass
class GateResult:
    """Output of a single governor decision."""
    max_tokens: int
    energy_mode: str
    mode_entered: bool              # True if mode changed this turn
    interventions: List[str]        # audit trail for this turn
    gate_applied: bool              # True if max_tokens is below unconstrained
    energy_snapshot: float
    turn: int


@dataclass
class TurnRecord:
    """One turn of causal data for α calibration."""
    turn: int
    prev_energy: float
    new_energy: float
    delta_energy: float
    response_len: int
    gate_applied: bool
    energy_mode: str
    interventions: List[str]
    timestamp: float = field(default_factory=time.time)


# --------------------------------------------------------------------------- #
# Governor
# --------------------------------------------------------------------------- #
class CognitiveGovernor:
    """Energy-coupled behavioral control.

    Thread-safe via a simple lock around mode state. Does not share state
    with being.state — reads energy from being.state each call.
    """

    def __init__(
        self,
        calibration_log: str = "logs/governor_calibration.jsonl",
        energy_min: float = 0.10,
    ):
        self._lock = threading.Lock()
        self._current_mode = "NORMAL"
        self._prev_energy: Optional[float] = None
        self._turn_records: List[TurnRecord] = []
        self._calibration_log = Path(calibration_log)
        self._calibration_log.parent.mkdir(parents=True, exist_ok=True)
        self.energy_min = energy_min
        self._fitted_alpha: Optional[float] = None
        
        # NEW: Asymmetric Recovery Parameters
        self.beta = 0.05  # Energy recovered during light rest
        self.light_rest_threshold = 200  # Max response length to qualify as rest

    # ---------------------------------------------------------------------- #
    # Primary decision point — call before every inference
    # ---------------------------------------------------------------------- #
    def apply(self, current_energy: float, turn: int) -> GateResult:
        """Evaluate energy state and return behavioral constraints.

        Call this BEFORE the inference call. Pass GateResult.max_tokens
        to the generation API. Log GateResult.interventions.
        """
        with self._lock:
            interventions: List[str] = []

            # Determine energy mode
            new_mode = self._compute_mode(current_energy)
            mode_entered = new_mode != self._current_mode
            if mode_entered:
                self._current_mode = new_mode
                interventions.append(f"MODE_ENTERED_{new_mode}")

            # Apply token gate
            unconstrained = ENERGY_MODES["NORMAL"]["max_tokens"]
            max_tokens = ENERGY_MODES[new_mode]["max_tokens"]
            gate_applied = max_tokens < unconstrained

            if gate_applied:
                interventions.append("TOKEN_GATE")

            return GateResult(
                max_tokens=max_tokens,
                energy_mode=new_mode,
                mode_entered=mode_entered,
                interventions=interventions,
                gate_applied=gate_applied,
                energy_snapshot=current_energy,
                turn=turn,
            )

    # ---------------------------------------------------------------------- #
    # Record causal turn data — call AFTER energy update in homeostasis
    # ---------------------------------------------------------------------- #
    def record_turn(
        self,
        prev_energy: float,
        new_energy: float,
        response_len: int,
        gate_result: Optional[GateResult] = None,
    ) -> TurnRecord:
        """Append causal event data. Applies light rest recovery if eligible."""
        
        interventions = gate_result.interventions if gate_result else []
        
        # 1. Check for Light Rest (Stabilization)
        if 0 < response_len < self.light_rest_threshold:
            # Override the drain with a recovery tick
            new_energy = min(1.0, prev_energy + self.beta)
            delta = prev_energy - new_energy  # Negative delta implies recovery
            interventions.append("LIGHT_REST_RECOVERY")
            
            # WHERE TO PLUG DATA: Push the recovered energy back to the Being state
            try:
                from drift.core.being import get_being
                get_being().state.energy = new_energy
            except Exception:
                pass
        else:
            delta = prev_energy - new_energy  # Standard drain (positive)

        record = TurnRecord(
            turn=gate_result.turn if gate_result else 0,
            prev_energy=prev_energy,
            new_energy=new_energy,
            delta_energy=delta,
            response_len=response_len,
            gate_applied=gate_result.gate_applied if gate_result else False,
            energy_mode=gate_result.energy_mode if gate_result else "UNKNOWN",
            interventions=interventions,
        )

        with self._lock:
            self._turn_records.append(record)
            self._append_calibration_log(record)
            
            # Verification: did the token gate actually reduce drain?
            # We skip this check if we just artificially recovered energy.
            if response_len >= self.light_rest_threshold:
                self._verify_intervention(record)

        return record

    # ---------------------------------------------------------------------- #
    # Verification — did the intervention work?
    # ---------------------------------------------------------------------- #
    def _verify_intervention(self, record: TurnRecord) -> None:
        """Closed-loop check: if gate was applied, was drain less than predicted?"""
        if not record.gate_applied:
            return
        if self._fitted_alpha is None:
            return   # can't verify without a calibrated α

        expected_drain = self._fitted_alpha * record.response_len
        actual_drain = record.delta_energy
        # Allow 20% tolerance
        if actual_drain > expected_drain * 1.20:
            # Gate reduced tokens but drain was still high — log the failure
            self._append_event({
                "event": "INTERVENTION_FAILED",
                "turn": record.turn,
                "gate_applied": True,
                "expected_drain": round(expected_drain, 6),
                "actual_drain": round(actual_drain, 6),
                "response_len": record.response_len,
                "note": "TOKEN_GATE did not reduce energy drain as predicted",
            })

    # ---------------------------------------------------------------------- #
    # α calibration
    # ---------------------------------------------------------------------- #
    def calibrate_alpha(self, min_samples: int = 20) -> Optional[float]:
        """Fit energy_drain = α * response_len from recorded turns.

        Returns None if insufficient data or no variance in response_len.
        Call this after a calibration session (30–50 turns, no token gate).
        """
        with self._lock:
            records = [r for r in self._turn_records if not r.gate_applied]

        if len(records) < min_samples:
            print(f"Insufficient data: {len(records)} ungated turns (need {min_samples})")
            return None

        drains = np.array([r.delta_energy for r in records])
        lengths = np.array([r.response_len for r in records])

        if lengths.std() < 1:
            print("No variance in response_len — cannot fit α. Run diverse prompts.")
            return None

        alpha = np.dot(lengths, drains) / np.dot(lengths, lengths)
        r = np.corrcoef(lengths, drains)[0, 1]

        print("\n=== α CALIBRATION RESULT ===")
        print(f"  n = {len(records)} ungated turns")
        print(f"  fitted α = {alpha:.6f}")
        print(f"  corr(response_len, drain) = {r:.3f}")
        print(f"  interpretation: each output character costs {alpha:.6f} energy units")
        if abs(r) < 0.3:
            print("  WARNING: weak correlation — energy may not be coupled to response length yet.")
            print("  Check that response_len is being passed through timing to update_needs.")
        elif alpha < 0:
            print("  WARNING: negative α — responses are recovering energy? Check sign convention.")
        else:
            print(f"  STATUS: calibration OK — update homeostasis.py effort cost with α={alpha:.6f}")

        self._fitted_alpha = alpha
        return alpha

    def summary(self) -> dict:
        """Quick health check — call from trajectory analysis."""
        with self._lock:
            records = self._turn_records
        if not records:
            return {"status": "no data", "turns": 0}

        drains = [r.delta_energy for r in records]
        modes = {}
        for r in records:
            modes[r.energy_mode] = modes.get(r.energy_mode, 0) + 1
        gated = sum(1 for r in records if r.gate_applied)

        return {
            "turns": len(records),
            "mean_drain_per_turn": round(sum(drains) / len(drains), 6),
            "gated_turns": gated,
            "mode_distribution": modes,
            "fitted_alpha": self._fitted_alpha,
        }

    # ---------------------------------------------------------------------- #
    # Private helpers
    # ---------------------------------------------------------------------- #
    def _compute_mode(self, energy: float) -> str:
        for mode, (lo, hi) in ENERGY_THRESHOLDS.items():
            if lo <= energy < hi:
                return mode
        return "CRITICAL"

    def _append_calibration_log(self, record: TurnRecord) -> None:
        entry = {
            "event": "TURN",
            "timestamp": record.timestamp,
            "turn": record.turn,
            "prev_energy": round(record.prev_energy, 6),
            "new_energy": round(record.new_energy, 6),
            "delta_energy": round(record.delta_energy, 6),
            "response_len": record.response_len,
            "gate_applied": record.gate_applied,
            "energy_mode": record.energy_mode,
            "interventions": record.interventions,
        }
        with self._calibration_log.open("a") as f:
            f.write(json.dumps(entry) + "\n")

    def _append_event(self, event: dict) -> None:
        event["timestamp"] = time.time()
        with self._calibration_log.open("a") as f:
            f.write(json.dumps(event) + "\n")


# === SELF-CHECK SYSTEM ===
def verify_beta_recovery():
    print("[*] Running Beta Recovery Self-Check...")
    try:
        gov = CognitiveGovernor(calibration_log="temp_beta_test.jsonl")
        
        # Mock GateResult
        class MockGate:
            turn = 1; gate_applied = False; energy_mode = "NORMAL"; interventions = []
            
        # Test 1: Heavy turn (no recovery)
        r_heavy = gov.record_turn(prev_energy=0.80, new_energy=0.75, response_len=1500, gate_result=MockGate())
        assert "LIGHT_REST_RECOVERY" not in r_heavy.interventions
        assert r_heavy.delta_energy > 0, "Heavy turn should drain energy"

        # Test 2: Light turn (triggers recovery)
        # Assuming homeostasis drained it to 0.74, governor should override it
        r_light = gov.record_turn(prev_energy=0.75, new_energy=0.74, response_len=50, gate_result=MockGate()) 
        assert "LIGHT_REST_RECOVERY" in r_light.interventions
        assert r_light.new_energy == 0.80, f"Energy should have recovered to 0.80, got {r_light.new_energy}"
        assert r_light.delta_energy < 0, "Delta should be negative (recovery)"

        print("[+] Beta Recovery Verified: System successfully recharges on light loads.")
    except AssertionError as e:
        print(f"[-] Verification Failed: {e}")
    except Exception as e:
        print(f"[-] Unexpected Error: {e}")
    finally:
        try:
            Path("temp_beta_test.jsonl").unlink()
        except OSError:
            pass


if __name__ == "__main__":
    verify_beta_recovery()
