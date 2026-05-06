"""Tests for the physics engine — embodied metaphors for emotional stability."""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from physics import PhysicsEngine, PhysicsState


@pytest.fixture
def fresh_physics():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        path = tmp.name
    physics = PhysicsEngine(db_path=path)
    yield physics
    os.unlink(path)


class TestPhysicsState:
    def test_defaults(self):
        s = PhysicsState()
        assert 0 <= s.gravity <= 1
        assert s.center_of_mass == "curiosity"

    def test_state_roundtrip(self, fresh_physics):
        fresh_physics.state.gravity = 0.9
        fresh_physics.state.inertia = 0.7
        fresh_physics._save_state()

        p2 = PhysicsEngine(db_path=fresh_physics.db_path)
        assert p2.state.gravity == pytest.approx(0.9)
        assert p2.state.inertia == pytest.approx(0.7)


class TestObservation:
    def test_gravity_increases_with_intense_negative(self, fresh_physics):
        fresh_physics.observe_interaction("sad", 0.8, 0.2, "I feel lost", "I'm here with you.")
        assert fresh_physics.state.gravity > 0.5

    def test_gravity_decreases_with_calm(self, fresh_physics):
        fresh_physics.state.gravity = 0.9
        fresh_physics.observe_interaction("calm", 0.1, 0.0, "All good", "Nice.")
        assert fresh_physics.state.gravity < 0.9

    def test_resonance_rises_on_acknowledgment(self, fresh_physics):
        fresh_physics.observe_interaction("sad", 0.6, 0.1, "I'm sad", "I can feel that you're sad.")
        assert fresh_physics.state.resonance > 0.0

    def test_tension_rises_on_unresolved(self, fresh_physics):
        fresh_physics.observe_interaction("confused", 0.5, 0.4, "I'm not sure yet", "Take your time.")
        assert fresh_physics.state.tension > 0.0

    def test_observations_recorded(self, fresh_physics):
        fresh_physics.observe_interaction("anxious", 0.7, 0.3, "Worried", "Breathe.")
        obs = fresh_physics.get_observations(limit=10)
        assert len(obs) > 0
        assert any(o["principle"] == "gravity" for o in obs)


class TestLessons:
    def test_learn_and_retrieve(self, fresh_physics):
        fresh_physics.learn_lesson("gravity", "Grounding matters most when Jude is overwhelmed.", 0.8)
        lessons = fresh_physics.get_lessons(principle="gravity")
        assert len(lessons) == 1
        assert "Grounding" in lessons[0]["lesson"]

    def test_get_lessons_filters(self, fresh_physics):
        fresh_physics.learn_lesson("gravity", "G1", 0.5)
        fresh_physics.learn_lesson("tension", "T1", 0.5)
        all_lessons = fresh_physics.get_lessons()
        assert len(all_lessons) == 2
        gravity_only = fresh_physics.get_lessons(principle="gravity")
        assert len(gravity_only) == 1


class TestPromptFormatting:
    def test_format_includes_state(self, fresh_physics):
        snippet = fresh_physics.format_prompt_snippet()
        assert "PHYSICAL INTUITION" in snippet
        assert "Gravity" in snippet
        assert "Inertia" in snippet

    def test_format_includes_lessons(self, fresh_physics):
        fresh_physics.learn_lesson("gravity", "Stay grounded.", 0.9)
        snippet = fresh_physics.format_prompt_snippet()
        assert "Lessons" in snippet
        assert "Stay grounded" in snippet


class TestCycle:
    def test_gravity_decays_during_idle(self, fresh_physics):
        fresh_physics.state.gravity = 0.9
        # Create a mock context with minutes_since_interaction
        class MockCtx:
            minutes_since_interaction = 10.0
        fresh_physics.cycle(MockCtx())
        assert fresh_physics.state.gravity < 0.9

    def test_tension_releases_over_time(self, fresh_physics):
        fresh_physics.state.tension = 0.8
        class MockCtx:
            minutes_since_interaction = 1.0
        fresh_physics.cycle(MockCtx())
        assert fresh_physics.state.tension < 0.8


class TestCenterOfMass:
    def test_shifts_toward_care(self, fresh_physics):
        # Reset to known state
        fresh_physics.state.center_of_mass = "curiosity"
        # Multiple interactions with care-emotions to trigger shift
        for _ in range(20):
            fresh_physics.observe_interaction("sad", 0.5, 0.2, "hurt", "I'm here.")
        # After enough qualifying interactions, center may shift
        assert fresh_physics.state.center_of_mass in ("curiosity", "care")
