"""Regression tests for isolation of mutable prompt-conflict rules."""

from drift.core.cognitive_orchestrator import ConflictDetector


def test_conflict_patterns_do_not_leak_between_detectors():
    first = ConflictDetector()
    second = ConflictDetector()
    original = second.CONTRADICTION_PATTERNS[:]
    first.CONTRADICTION_PATTERNS.append(("alpha", "beta", "injected"))
    assert second.CONTRADICTION_PATTERNS == original


def test_fresh_detector_uses_original_patterns():
    first = ConflictDetector()
    first.CONTRADICTION_PATTERNS.clear()
    assert ConflictDetector().CONTRADICTION_PATTERNS
