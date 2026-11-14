"""Regression tests for prompt conflict arbitration.

These tests intentionally exercise observable behavior, not just conflict logging.
"""
from copy import deepcopy

from core.cognitive_orchestrator import ConflictDetector


def test_lower_priority_conflicting_instruction_is_removed():
    detector = ConflictDetector()
    sections = {
        "safety": ["Be direct when describing confirmed security failures."],
        "style": ["Be gentle when responding to emotional concerns."],
    }
    original = deepcopy(sections)
    conflicts = detector.detect(sections)
    assert conflicts, "Expected conflict to be detected"

    resolved = detector.resolve(conflicts, sections, {"safety": 100, "style": 10})

    assert resolved["safety"] == original["safety"]
    assert not any("be gentle" in s.lower() for s in resolved["style"])
    assert any(c.resolution and c.resolution != "noted: both voices present" for c in conflicts)


def test_no_conflict_keeps_sections_unchanged():
    detector = ConflictDetector()
    sections = {"safety": ["Protect user secrets."], "style": ["Be concise."]}
    assert detector.resolve(detector.detect(sections), sections, {"safety": 100, "style": 10}) == sections


def test_conflict_resolution_does_not_mutate_original_sections():
    detector = ConflictDetector()
    sections = {"high": ["Be direct."], "low": ["Be gentle."]}
    before = deepcopy(sections)
    detector.resolve(detector.detect(sections), sections, {"high": 100, "low": 10})
    assert sections == before
