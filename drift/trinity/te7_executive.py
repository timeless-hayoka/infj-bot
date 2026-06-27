from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from .calibrate_trinity import calibrate


class TrinityExecutive:
    DEFAULT_PROFILE = {
        'dmU_weight': 0.30,
        'reasoning_weight': 0.25,
        'imagination_weight': 0.15,
        'validation_weight': 0.20,
        'output_gate_weight': 0.05,
        'executive_control_weight': 0.05,
    }

    MODE_PROFILES = {
        'grounded': {
            'dmU_weight': 0.35,
            'reasoning_weight': 0.30,
            'imagination_weight': 0.05,
            'validation_weight': 0.20,
            'output_gate_weight': 0.05,
            'executive_control_weight': 0.05,
        },
        'hybrid': {
            'dmU_weight': 0.30,
            'reasoning_weight': 0.25,
            'imagination_weight': 0.15,
            'validation_weight': 0.20,
            'output_gate_weight': 0.05,
            'executive_control_weight': 0.05,
        },
        'exploratory': {
            'dmU_weight': 0.22,
            'reasoning_weight': 0.23,
            'imagination_weight': 0.30,
            'validation_weight': 0.15,
            'output_gate_weight': 0.05,
            'executive_control_weight': 0.05,
        },
    }

    def __init__(self, weights):
        self.w = dict(weights or {})

    @staticmethod
    def _clamp_unit(value: Any) -> float:
        try:
            score = float(value)
        except (TypeError, ValueError):
            return 0.0
        return max(0.0, min(1.0, score))

    @staticmethod
    def _normalize(profile: Mapping[str, float]) -> dict[str, float]:
        bounded = {key: max(0.0, float(value)) for key, value in profile.items()}
        total = sum(bounded.values())
        if total <= 0:
            return dict(profile)
        return {key: round(value / total, 4) for key, value in bounded.items()}

    def select_mode(self, context):
        context = context or {}
        ambiguity = self._clamp_unit(context.get('ambiguity', 0))
        risk = self._clamp_unit(context.get('risk', 0))
        novelty = self._clamp_unit(context.get('novelty', 0))

        signal_pressure = (ambiguity * 0.34) + (risk * 0.36) + (novelty * 0.30)
        strongest_signal = max(ambiguity, risk, novelty)

        if signal_pressure < 0.24 and strongest_signal < 0.25:
            return 'grounded'
        if signal_pressure < 0.58:
            return 'hybrid'
        return 'exploratory'

    def allocate_weights(self, mode, history=None):
        profile = deepcopy(self.MODE_PROFILES.get(mode, self.MODE_PROFILES['exploratory']))
        history = history or {}

        if history:
            profile = calibrate(history, profile)

        return self._normalize(profile)
