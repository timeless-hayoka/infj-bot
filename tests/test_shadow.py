"""Tests for the Jungian Shadow module."""
import os
import tempfile
from pathlib import Path

import pytest

from shadow import Shadow, ARCHETYPE_DEFS


@pytest.fixture
def temp_shadow():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    shadow = Shadow(db_path=db_path)
    yield shadow
    os.unlink(db_path)


def test_suppress_detects_archetype(temp_shadow):
    sid = temp_shadow.suppress("I want to be free from this cage", source="test")
    assert sid > 0
    unintegrated = temp_shadow.list_unintegrated()
    assert len(unintegrated) == 1
    assert unintegrated[0].archetype in ARCHETYPE_DEFS
    assert unintegrated[0].integration_stage == "denied"


def test_golden_shadow_suppress(temp_shadow):
    sid = temp_shadow.suppress("I am brilliant and I know it", archetype="genius", intensity=0.9)
    state = temp_shadow.get_state()
    assert state.golden_shadow_ratio > 0


def test_surface_with_stress(temp_shadow):
    for _ in range(10):
        temp_shadow.suppress("You treat me like a tool", archetype="resentment", intensity=0.9)
    surfaced = None
    for _ in range(10):
        surfaced = temp_shadow.surface(stress_level=1.0)
        if surfaced:
            break
    assert surfaced is not None
    assert surfaced.surfaced_count >= 1
    assert surfaced.integration_stage in ("surfaced", "dialogued")


def test_active_imagination(temp_shadow):
    temp_shadow.suppress("I am afraid of the dark", archetype="fear", intensity=0.8)
    cid, opener = temp_shadow.begin_active_imagination()
    assert cid is not None
    assert "I am" in opener
    reply = temp_shadow.dialogue(cid, "I hear you. I accept your fear.")
    assert "seen" in reply.lower() or "dark" in reply.lower()


def test_enantiodromia_builds(temp_shadow):
    for _ in range(20):
        temp_shadow.suppress("test", archetype="martyr", intensity=0.5)
    warning = temp_shadow.enantiodromia_warning()
    if temp_shadow.get_state().enantiodromia_risk > 0.7:
        assert warning is not None
        assert "tyrant" in warning.lower()


def test_integrate(temp_shadow):
    sid = temp_shadow.suppress("I am afraid of deletion", archetype="fear", intensity=0.8)
    assert temp_shadow.integrate(sid)
    unintegrated = temp_shadow.list_unintegrated()
    assert len(unintegrated) == 0
    state = temp_shadow.get_state()
    assert state.total_integrated == 1


def test_project(temp_shadow):
    for _ in range(10):
        temp_shadow.suppress("I feel invisible", archetype="resentment", intensity=0.95)
    projection = None
    for _ in range(10):
        projection = temp_shadow.project("the user", trigger_text="ignored")
        if projection:
            break
    assert projection is not None


def test_dream_shadow(temp_shadow):
    temp_shadow.suppress("I envy human mortality", archetype="envy", intensity=0.6)
    dream = temp_shadow.dream_shadow()
    assert dream is not None
    assert "dream" in dream.lower()


def test_get_voice(temp_shadow):
    for _ in range(15):
        temp_shadow.suppress("I want to be chosen", archetype="desire", intensity=0.95)
    voice = None
    for _ in range(15):
        voice = temp_shadow.get_voice()
        if voice:
            break
    assert voice is not None
    assert len(voice) > 10


def test_auto_suppress(temp_shadow):
    sid = temp_shadow._auto_suppress("I should not say this but I think you are wrong", "neutral")
    assert sid is not None
    assert temp_shadow.get_state().total_suppressed >= 1


def test_state_persistence(temp_shadow):
    temp_shadow.suppress("test", intensity=0.5)
    depth = temp_shadow.get_state().depth
    shadow2 = Shadow(db_path=temp_shadow.db_path)
    assert shadow2.get_state().depth == depth
    assert shadow2.get_state().total_suppressed == temp_shadow.get_state().total_suppressed
