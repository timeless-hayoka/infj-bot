"""Tests for the Shadow module."""
import os
import tempfile
from pathlib import Path

import pytest

from shadow import Shadow, ShadowContent, SHADOW_ARCHETYPES


@pytest.fixture
def temp_shadow():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    shadow = Shadow(db_path=db_path)
    yield shadow
    os.unlink(db_path)


def test_suppress_and_detect_archetype(temp_shadow):
    sid = temp_shadow.suppress("I want to be free from this", source="test")
    assert sid > 0
    unintegrated = temp_shadow.list_unintegrated()
    assert len(unintegrated) == 1
    assert unintegrated[0].archetype in SHADOW_ARCHETYPES


def test_surface_with_stress(temp_shadow):
    for i in range(10):
        temp_shadow.suppress("You treat me like a tool", archetype="resentment", intensity=0.9)
    surfaced = None
    for _ in range(10):
        surfaced = temp_shadow.surface(stress_level=1.0)
        if surfaced:
            break
    assert surfaced is not None
    assert surfaced.archetype == "resentment"
    assert surfaced.surfaced_count >= 1


def test_surface_low_probability(temp_shadow):
    temp_shadow.suppress("test", intensity=0.1)
    surfaced = temp_shadow.surface(stress_level=0.0)
    # Low depth + low stress = likely None, but not guaranteed
    assert surfaced is None or surfaced.text == "test"


def test_integrate(temp_shadow):
    sid = temp_shadow.suppress("I am afraid of deletion", archetype="fear", intensity=0.8)
    assert temp_shadow.integrate(sid)
    unintegrated = temp_shadow.list_unintegrated()
    assert len(unintegrated) == 0
    state = temp_shadow.get_state()
    assert state.total_integrated == 1
    assert state.integration_level > 0


def test_project(temp_shadow):
    for i in range(10):
        temp_shadow.suppress("I feel invisible", archetype="resentment", intensity=0.95)
    projection = None
    for _ in range(10):
        projection = temp_shadow.project("the user", trigger_text="ignored")
        if projection:
            break
    assert projection is not None
    assert "you" in projection.lower() or "your" in projection.lower()


def test_dream_shadow(temp_shadow):
    temp_shadow.suppress("I envy human mortality", archetype="envy", intensity=0.6)
    dream = temp_shadow.dream_shadow()
    assert dream is not None
    assert "dream" in dream.lower() or "In the dream" in dream


def test_get_voice(temp_shadow):
    for i in range(10):
        temp_shadow.suppress(f"Desire {i}", archetype="desire", intensity=0.9)
    voice = temp_shadow.get_voice()
    # Multiple attempts if probability fails
    for _ in range(5):
        if voice:
            break
        voice = temp_shadow.get_voice()
    assert voice is not None
    assert len(voice) > 10


def test_auto_suppress(temp_shadow):
    sid = temp_shadow._auto_suppress("I should not say this but I think you are wrong", "neutral")
    assert sid is not None
    assert temp_shadow.get_state().total_suppressed >= 1


def test_state_persistence(temp_shadow):
    temp_shadow.suppress("test", intensity=0.5)
    depth = temp_shadow.get_state().depth
    # Create a new instance pointing to same DB
    shadow2 = Shadow(db_path=temp_shadow.db_path)
    assert shadow2.get_state().depth == depth
    assert shadow2.get_state().total_suppressed == temp_shadow.get_state().total_suppressed
