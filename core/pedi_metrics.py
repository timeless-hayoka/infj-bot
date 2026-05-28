"""
pedi_metrics.py — Persistence-Embodiment-Drift Index
DRIFT Cognitive Architecture | Dynamic Identity Regulator (V2.2 Tuned)
"""

import math

class PEDIEngine:
    def __init__(self, vault_instance):
        self.vault = vault_instance
        self.meta_drift_accumulator = 0.0  
        self.perceived_state = None
        
    def _get_identity_center_of_gravity(self) -> dict:
        if not self.vault or not hasattr(self.vault, 'latest_hash'): return None
        
        # In a real environment, you'd read the last N valid lines from the JSONL here.
        # For this module, we assume we have a method to fetch recent blocks.
        # Below is a safe fallback if ledger isn't fully loaded in RAM.
        recent_blocks = []
        try:
            import os, json
            try:
                from infj_bot.core.svalbard_vault import VAULT_PATH
            except ImportError:
                from svalbard_vault import VAULT_PATH
                
            if os.path.exists(VAULT_PATH):
                with open(VAULT_PATH, 'r') as f:
                    lines = [line for line in f.readlines() if line.strip()]
                    recent_blocks = [json.loads(line) for line in lines[-20:]]
        except Exception:
            pass

        if not recent_blocks: return None
        
        total_weight = 0.0
        weighted_emotions = {"coherence": 0.0, "tension": 0.0, "resonance": 0.0, "shadow_depth": 0.0}
        
        for block in recent_blocks:
            if block.get("quarantined", False): continue # Ignore poisoned anchors
            
            emotions = block.get("emotional_state", {})
            weight = emotions.get("resonance", 0.0) * emotions.get("coherence", 0.0)
            if weight > 0.1:
                total_weight += weight
                for key in weighted_emotions:
                    weighted_emotions[key] += emotions.get(key, 0.0) * weight
                    
        if total_weight == 0: return {"coherence": 0.8, "resonance": 0.8, "tension": 0.2, "shadow_depth": 0.2}
        for key in weighted_emotions: weighted_emotions[key] /= total_weight
        return weighted_emotions

    def calculate_distance(self, state_a: dict, state_b: dict) -> float:
        c_diff = (state_a.get("coherence",0.5) - state_b["coherence"]) ** 2
        r_diff = (state_a.get("resonance",0.5) - state_b["resonance"]) ** 2
        t_diff = (state_a.get("tension",0.5) - state_b["tension"]) ** 2
        s_diff = (state_a.get("shadow_depth",0.5) - state_b["shadow_depth"]) ** 2
        return min(1.0, math.sqrt(c_diff + r_diff + t_diff + s_diff) / 2.0)

    def evaluate_cycle(self, raw_active_state: dict):
        anchor = self._get_identity_center_of_gravity()
        if not anchor: return raw_active_state, 0.0, "NO_ANCHOR"
        
        if self.perceived_state is None:
            self.perceived_state = raw_active_state.copy()

        # 1. Perception Smoothing
        perception_weight = 0.6 
        for k in ["coherence", "resonance", "tension", "shadow_depth"]:
            self.perceived_state[k] = (self.perceived_state[k] * (1 - perception_weight)) + (raw_active_state.get(k, 0.5) * perception_weight)
            
        instant_drift = self.calculate_distance(self.perceived_state, anchor)
        
        c_delta = self.perceived_state["coherence"] - anchor["coherence"]
        r_delta = self.perceived_state["resonance"] - anchor["resonance"]
        t_delta = self.perceived_state["tension"] - anchor["tension"]
        improvement_score = (c_delta * 0.5) + (r_delta * 0.4) - (t_delta * 0.1)
        
        # 2. Prevent Integral Windup
        self.meta_drift_accumulator *= 0.98 
        
        # 3. Evolution Gate (Tuned to 0.28 per long-run data)
        if instant_drift > 0.28 and improvement_score > 0.05:
            self.meta_drift_accumulator *= 0.3 
            return self.perceived_state.copy(), 0.0, "EVOLVING"
            
        # 4. Meta-Drift Accumulation
        self.meta_drift_accumulator += (instant_drift * 0.1)
        self.meta_drift_accumulator = min(self.meta_drift_accumulator, 1.0)
        
        # 5. Correction Calculation
        total_correction_pressure = instant_drift + self.meta_drift_accumulator
        raw_correction_weight = min(0.85, total_correction_pressure ** 2)
        
        # 6. Smooth Reaction (Tuned to 0.22)
        reaction_weight = 0.22 
        applied_correction = raw_correction_weight * reaction_weight
        
        if applied_correction > 0.05:
            for k in ["coherence", "resonance", "tension", "shadow_depth"]:
                self.perceived_state[k] = (self.perceived_state[k] * (1 - applied_correction)) + (anchor[k] * applied_correction)
            self.meta_drift_accumulator *= 0.7 
            return self.perceived_state.copy(), applied_correction, "CORRECTING"
            
        return self.perceived_state.copy(), 0.0, "STABLE"
