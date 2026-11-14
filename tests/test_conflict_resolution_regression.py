"""Regression tests for prompt conflict arbitration.

These tests intentionally exercise observable behavior, not just conflict logging.
"""
from copy import deepcopy

from core.cognitive_orchestrator import ConflictDetector


def test_different_scopes_are_not_treated_as_conflicting():
    detector = ConflictDetector()
    sections = {
        "safety": ["Be direct when describing confirmed security failures."],
        "style": ["Be gentle when responding to emotional concerns."],
    }
    original = deepcopy(sections)
    conflicts = detector.detect(sections)
    assert not conflicts, "Direct security reporting and gentle emotional responses are compatible"

    resolved = detector.resolve(conflicts, sections, {"safety": 100, "style": 10})

    assert resolved["safety"] == original["safety"]
    assert resolved["style"] == original["style"]



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


def test_explicit_conflicting_directives_are_detected():
    detector = ConflictDetector()
    sections = {'core': ['Always be direct in all replies.'], 'style': ['Always be gentle in all replies.']}
    conflicts = detector.detect(sections)
    assert conflicts
    resolved = detector.resolve(conflicts, sections, {'core': 100, 'style': 10})
    assert resolved['core'] == sections['core']
    assert resolved['style'] == []
