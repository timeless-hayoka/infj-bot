from __future__ import annotations

from typing import Any, Iterable


class RealityAnchor:
    """
    Validates hypotheses against a set of prohibited patterns.

    Constraints are prohibited-term strings that, if present in the
    hypothesis metadata, indicate a hallucinated or test-fixture-contaminated
    result. The raw hypothesis text is intentionally not part of the match.
    """

    _METADATA_FIELDS = ('type', 'label', 'category', 'flag', 'source')

    def __init__(self, approval_threshold: float = 0.8):
        self.approval_threshold = approval_threshold

    @staticmethod
    def _flatten_constraint(constraint: Any) -> str:
        if isinstance(constraint, dict):
            pieces = []
            for value in constraint.values():
                if value is None:
                    continue
                if isinstance(value, (list, tuple, set)):
                    pieces.extend(str(item) for item in value if item is not None)
                else:
                    pieces.append(str(value))
            return ' '.join(pieces).lower().strip()
        return str(constraint).lower().strip()

    def validate(self, hypothesis: dict, constraints: list) -> dict:
        violations = []
        metadata_blob = ' '.join(str(hypothesis.get(field, '')) for field in self._METADATA_FIELDS).lower()

        for constraint in constraints or []:
            needle = self._flatten_constraint(constraint)
            if needle and needle in metadata_blob:
                violations.append(needle)

        score = max(0.0, 1.0 - (len(violations) * 0.5))
        approved = score >= self.approval_threshold and not violations

        return {
            'approved': approved,
            'score': round(score, 4),
            'violations': len(violations),
            'violation_detail': violations,
        }
