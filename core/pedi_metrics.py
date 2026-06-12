"""
pedi_metrics.py — Persistence-Embodiment-Drift Index
DRIFT Cognitive Architecture | Dynamic Identity Regulator (V2.2 Tuned)
"""

import math
from dataclasses import dataclass
from typing import Dict

# DIMS defines the dimensions used for anchor distance calculations in PEDI.
# Note: Real Svalbard ledger blocks also store 'shadow_depth' at the root of 'emotional_state'
# (making four dimensions tracked in total), but 'shadow_depth' is intentionally excluded
# from the anchor distance calculation to align with the paper's 3D state space model.
DIMS = ("coherence", "resonance", "tension")
NORM = 1.5
MIN_USABLE_BLOCKS = 3
FALLBACK_ANCHOR = {"coherence": 0.85, "resonance": 0.82, "tension": 0.12}

@dataclass
class AnchorResult:
    anchor: Dict[str, float]
    valid: bool
    reason: str

class PEDIEngine:
    def __init__(self, vault_instance):
        self.vault = vault_instance
        self.meta_drift_accumulator = 0.0  
        self.perceived_state = None
        
    def _get_identity_center_of_gravity(self) -> AnchorResult:
        if not self.vault or not hasattr(self.vault, 'latest_hash'):
            return AnchorResult(FALLBACK_ANCHOR, False, "no_vault")
        
        recent_blocks = []
        try:
            import os
            import json
            try:
                from infj_bot.core.svalbard_vault import VAULT_PATH
            except ImportError:
                from svalbard_vault import VAULT_PATH
                
            if os.path.exists(VAULT_PATH):
                with open(VAULT_PATH, 'r', encoding='utf-8') as f:
                    lines = [line for line in f.readlines() if line.strip()]
                    recent_blocks = [json.loads(line) for line in lines[-20:]]
        except Exception as e:
            return AnchorResult(FALLBACK_ANCHOR, False, f"read_error: {str(e)}")

        if not recent_blocks:
            return AnchorResult(FALLBACK_ANCHOR, False, "no_blocks")
            
        def _is_degenerate(block) -> bool:
            emotions = block.get("emotional_state", {})
            return emotions.get("coherence", 0.0) < 1e-6 and emotions.get("resonance", 0.0) < 1e-6

        usable = [b for b in recent_blocks if not b.get("quarantined", False) and not _is_degenerate(b)]
        
        if len(usable) < MIN_USABLE_BLOCKS:
            return AnchorResult(FALLBACK_ANCHOR, False, "cold_start")
            
        total_weight = 0.0
        weighted_emotions = {"coherence": 0.0, "resonance": 0.0, "tension": 0.0}
        
        for block in usable:
            emotions = block.get("emotional_state", {})
            weight = emotions.get("resonance", 0.0) * emotions.get("coherence", 0.0)
            if weight > 0.1:
                total_weight += weight
                for key in DIMS:
                    weighted_emotions[key] += emotions.get(key, 0.0) * weight
                    
        if total_weight == 0:
            for block in usable:
                emotions = block.get("emotional_state", {})
                for key in DIMS:
                    weighted_emotions[key] += emotions.get(key, 0.0)
            for key in DIMS:
                weighted_emotions[key] /= len(usable)
        else:
            for key in DIMS:
                weighted_emotions[key] /= total_weight
                
        return AnchorResult(weighted_emotions, True, "ok")

    def calculate_distance(self, state_a: dict, state_b: dict) -> float:
        sum_sq = sum((state_a.get(dim, 0.5) - state_b.get(dim, 0.5)) ** 2 for dim in DIMS)
        return min(1.0, math.sqrt(sum_sq) / NORM)

    def evaluate_cycle(self, raw_active_state: dict):
        ar = self._get_identity_center_of_gravity()
        
        if self.perceived_state is None:
            self.perceived_state = raw_active_state.copy()
            
        if not ar.valid:
            for k in raw_active_state:
                if k not in self.perceived_state:
                    self.perceived_state[k] = raw_active_state[k]
            return self.perceived_state.copy(), 0.0, f"HOLD_{ar.reason.upper()}"
            
        anchor = ar.anchor
        
        # 1. Perception Smoothing
        perception_weight = 0.6 
        for k in DIMS:
            self.perceived_state[k] = (self.perceived_state.get(k, 0.5) * (1 - perception_weight)) + (raw_active_state.get(k, 0.5) * perception_weight)
            
        for k in raw_active_state:
            if k not in DIMS:
                self.perceived_state[k] = raw_active_state[k]
                
        instant_drift = self.calculate_distance(self.perceived_state, anchor)
        
        c_delta = self.perceived_state.get("coherence", 0.5) - anchor["coherence"]
        r_delta = self.perceived_state.get("resonance", 0.5) - anchor["resonance"]
        t_delta = self.perceived_state.get("tension", 0.0) - anchor["tension"]
        improvement_score = (c_delta * 0.5) + (r_delta * 0.4) - (t_delta * 0.1)
        
        # 2. Prevent Integral Windup
        self.meta_drift_accumulator *= 0.98 
        
        # 3. Evolution Gate
        if instant_drift > 0.28 and improvement_score > 0.05:
            self.meta_drift_accumulator *= 0.3 
            return self.perceived_state.copy(), 0.0, "EVOLVING"
            
        # 4. Meta-Drift Accumulation
        self.meta_drift_accumulator += (instant_drift * 0.1)
        self.meta_drift_accumulator = min(self.meta_drift_accumulator, 1.0)
        
        # 5. Correction Calculation
        total_correction_pressure = instant_drift + self.meta_drift_accumulator
        raw_correction_weight = min(0.85, total_correction_pressure ** 2)
        
        # 6. Smooth Reaction
        reaction_weight = 0.22 
        applied_correction = raw_correction_weight * reaction_weight
        
        if applied_correction > 0.05:
            for k in DIMS:
                self.perceived_state[k] = (self.perceived_state.get(k, 0.5) * (1 - applied_correction)) + (anchor[k] * applied_correction)
            self.meta_drift_accumulator *= 0.7 
            return self.perceived_state.copy(), applied_correction, "CORRECTING"
            
        return self.perceived_state.copy(), 0.0, "STABLE"
