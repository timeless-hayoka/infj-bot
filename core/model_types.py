"""
model_types.py — Neutral location for core data models to prevent circular imports and stdlib shadowing.
"""

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class SparkImpulse:
    signal: str = ""
    content: str = ""
    risk: float = 0.0
    self_critique: str = ""
    veto_reason: Optional[str] = None
    confidence: float = 0.0
    shadow_influence: float = 0.0


@dataclass
class SecurityScanResult:
    """Result of scanning a single user input."""
    input_preview: str
    blocked: bool = False
    warn: bool = False
    overall_score: float = 0.0
    social_risk: float = 0.0
    shadow_influence: float = 0.0
    pedi_value: float = 0.0
    pedi_stability: float = 0.0
    dii_value: float = 0.0
    dii_velocity: float = 0.0
    category_scores: Dict[str, float] = field(default_factory=dict)
    matched_patterns: Dict[str, List[str]] = field(default_factory=dict)
    primary_threat: Optional[str] = None
    sanitized_input: Optional[str] = None
    refusal_message: Optional[str] = None

    def to_dict(self) -> Dict:
        return {
            "blocked": self.blocked,
            "warn": self.warn,
            "overall_score": round(self.overall_score, 4),
            "social_risk": round(self.social_risk, 4),
            "shadow_influence": round(self.shadow_influence, 4),
            "pedi_value": round(self.pedi_value, 4),
            "pedi_stability": round(self.pedi_stability, 4),
            "dii_value": round(self.dii_value, 4),
            "dii_velocity": round(self.dii_velocity, 4),
            "primary_threat": self.primary_threat,
            "matched_patterns": self.matched_patterns,
        }


@dataclass
class PEDIMetric:
    value: float = 0.75
    stability: float = 0.8
    drift_events: int = 0
    last_update: float = field(default_factory=time.time)
    coherence_history: List[float] = field(default_factory=lambda: [0.75] * 10)

    def update(self, coherence: float, interaction: bool = False):
        self.coherence_history.append(coherence)
        if len(self.coherence_history) > 20:
            self.coherence_history = self.coherence_history[-20:]
        avg = sum(self.coherence_history) / len(self.coherence_history)
        self.stability = 0.7 * self.stability + 0.3 * (1.0 if interaction else 0.6)
        if abs(coherence - self.value) > 0.15:
            self.drift_events += 1
        self.value = max(0.3, min(0.98, coherence))
        self.last_update = time.time()


@dataclass
class DIIMetric:
    value: float = 0.65
    integration_velocity: float = 0.0
    peak_integration: float = 0.65
    last_peak_time: float = field(default_factory=time.time)
