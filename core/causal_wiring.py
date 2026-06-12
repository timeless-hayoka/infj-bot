import contextvars
from typing import Dict, List, Optional, Any

# ContextVar for active state override during a request lifecycle
state_override_var: contextvars.ContextVar[Optional[Dict[str, Any]]] = contextvars.ContextVar("state_override", default=None)

# ContextVar for active generation parameters (temperature, top_p, etc.) calculated for the turn
generation_params_var: contextvars.ContextVar[Optional[Dict[str, Any]]] = contextvars.ContextVar("generation_params", default=None)

# ContextVar for retrieved memory keys during a request lifecycle
retrieved_memory_keys_var: contextvars.ContextVar[List[str]] = contextvars.ContextVar("retrieved_memory_keys", default=[])


def pedi_to_weights(pedi_state: dict) -> dict:
    def _get(key, default):
        val = pedi_state.get(key, default)
        if isinstance(val, dict):
            return float(val.get("current", default))
        return float(val)

    return {
        "memory_weight": 1.0 + _get("resonance", 0.5),
        "emotional_bias": _get("coherence", 0.5),
        "temporal_priority": _get("tension", 0.1),
        "reasoning_depth": 1.0 + _get("coherence", 0.5)
    }


def dii_to_generation_params(dii_state: float) -> dict:
    # low DII -> deterministic, high DII -> exploratory
    return {
        "temperature": 0.3 + (dii_state * 1.2),
        "top_p": max(0.5, 1.0 - dii_state),
        "response_exploration": dii_state > 0.1
    }


def homeostasis_gate(homeo_state: dict) -> dict:
    return {
        "model_selection": "strong" if homeo_state.get("crisis", 0.0) > 0.7 else "fast",
        "refusal_sensitivity": homeo_state.get("stress", 0.5),
        "verbosity": 1.0 + homeo_state.get("energy", 0.5),
        "memory_access": homeo_state.get("fatigue", 0.0) < 0.6
    }


def global_workspace_bottleneck(state: dict, memory_matches: list, query: str) -> list:
    """Ranks signals and creates an attention bottleneck."""
    signals = [("query", 1.0)]
    
    for mem in memory_matches:
        signals.append(("pedi_memory_match", mem.get("score", 0.5)))
        
    signals.append(("dii_uncertainty", state.get("dii", 0.5)))
    signals.append(("homeostasis_pressure", state.get("homeostasis", {}).get("stress", 0.5)))
    
    signals.sort(key=lambda x: x[1], reverse=True)
    return [s[0] for s in signals[:3]] # Only top 3 signals pass the bottleneck
