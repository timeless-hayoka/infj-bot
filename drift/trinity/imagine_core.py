from __future__ import annotations

import math
from typing import Any


class ImagineCore:
    def __init__(self, hallucination_budget=0.1, confidence_threshold=0.72):
        self.budget = float(hallucination_budget)
        self.confidence_threshold = float(confidence_threshold)
        self.high_risk_keywords = {
            'call', 'delegatecall', 'selfdestruct', 'suicide',
            'tx.origin', 'block.timestamp', 'block.number', 'abi.encodePacked',
            'unchecked', 'assembly', 'ecrecover'
        }

    @staticmethod
    def _clamp01(value: Any, default: float = 0.0) -> float:
        try:
            score = float(value)
        except (TypeError, ValueError):
            return default
        return max(0.0, min(1.0, score))

    def _signal_blob(self, signal: Any) -> str:
        if isinstance(signal, dict):
            parts = []
            for key in ('hypothesis', 'summary', 'description', 'label', 'type', 'source', 'flag'):
                value = signal.get(key)
                if value:
                    parts.append(str(value))
            return ' '.join(parts).lower()
        return str(signal).lower()

    def _score_signal(self, signal: Any, index: int, total: int, novelty: float) -> dict[str, Any]:
        signal_blob = self._signal_blob(signal)
        is_oob = isinstance(signal, dict) and signal.get('type') == 'oob_vuln'

        keyword_count = sum(1 for keyword in self.high_risk_keywords if keyword in signal_blob)
        keyword_score = min(1.0, math.log1p(keyword_count) / math.log1p(4)) * 0.55
        novelty_score = novelty * 0.25
        freshness_score = max(0.0, (1.0 - (index / max(1, total))) * 0.15)

        if is_oob:
            keyword_score = max(keyword_score, 0.60)
            novelty_score = max(novelty_score, 0.25)
            freshness_score = max(freshness_score, 0.10)

        confidence = min(1.0, keyword_score + novelty_score + freshness_score)
        hypothesis_text = 'possible edge case in signal {}'.format(index)
        if isinstance(signal, dict):
            hypothesis_text = signal.get('hypothesis') or signal.get('summary') or hypothesis_text

        return {
            'hypothesis': hypothesis_text,
            'confidence': round(confidence, 4),
            'type': 'oob_vuln' if is_oob else 'speculative',
            'budget_cost': 0.05 if is_oob else 0.02,
            'signal_index': index,
            'signal_blob': signal_blob,
        }

    def generate_hypotheses(self, context):
        context = context or {}
        if context.get('mode') == 'grounded':
            return []

        seeds = list(context.get('signals', []) or [])
        if not seeds:
            return []

        novelty = self._clamp01(context.get('novelty', 0.0))
        threshold = self._clamp01(context.get('confidence_threshold', self.confidence_threshold), default=self.confidence_threshold)
        budget = self._clamp01(context.get('hallucination_budget', self.budget), default=self.budget)

        scored = [self._score_signal(signal, index, len(seeds), novelty) for index, signal in enumerate(seeds)]
        scored.sort(key=lambda item: item['confidence'], reverse=True)

        filtered = [item for item in scored if item['confidence'] >= threshold]
        if not filtered:
            best = scored[0]
            if best['confidence'] >= min(threshold, 0.5):
                filtered = [best]

        max_candidates = max(1, int(math.ceil(len(seeds) * budget)))
        return filtered[:max_candidates]
