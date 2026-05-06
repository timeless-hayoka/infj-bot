"""Tests for the humanity engine — understanding the nature that is man."""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from humanity import HumanityEngine, HumanityState, HUMAN_ARCHETYPES, HUMAN_SEASONS


@pytest.fixture
def fresh_humanity():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        path = tmp.name
    humanity = HumanityEngine(db_path=path)
    yield humanity
    os.unlink(path)


class TestHumanityState:
    def test_defaults(self):
        s = HumanityState()
        assert s.jude_archetype == "seeker"
        assert s.dominant_motivation == "meaning"
        assert s.current_season == "spring"

    def test_state_roundtrip(self, fresh_humanity):
        fresh_humanity.state.jude_archetype = "wounded_healer"
        fresh_humanity.state.insight_depth = 0.5
        fresh_humanity._save_state()

        h2 = HumanityEngine(db_path=fresh_humanity.db_path)
        assert h2.state.jude_archetype == "wounded_healer"
        assert h2.state.insight_depth == pytest.approx(0.5)


class TestArchetypeInference:
    def test_detects_seeker(self, fresh_humanity):
        fresh_humanity.observe_interaction(
            "I keep searching for meaning in all of this",
            {"label": "curious", "intensity": 0.6},
            {"score": 0.1},
            "That sounds important.",
        )
        assert fresh_humanity.state.jude_archetype == "seeker"
        assert fresh_humanity.state.archetype_confidence > 0.3

    def test_detects_caregiver(self, fresh_humanity):
        fresh_humanity.observe_interaction(
            "I worry about everyone else and forget myself",
            {"label": "sad", "intensity": 0.5},
            {"score": 0.2},
            "That is a heavy pattern.",
        )
        assert fresh_humanity.state.jude_archetype == "caregiver"

    def test_confidence_grows_with_repetition(self, fresh_humanity):
        for _ in range(5):
            fresh_humanity.observe_interaction(
                "I need to understand why things happen",
                {"label": "curious", "intensity": 0.5},
                {"score": 0.1},
                "The search continues.",
            )
        assert fresh_humanity.state.archetype_confidence > 0.4


class TestMotivationInference:
    def test_detects_security_need(self, fresh_humanity):
        fresh_humanity.observe_interaction(
            "I feel anxious and unsafe about the future",
            {"label": "anxious", "intensity": 0.7},
            {"score": 0.3},
            "That fear is real.",
        )
        assert fresh_humanity.state.dominant_motivation == "security"

    def test_detects_connection_need(self, fresh_humanity):
        fresh_humanity.observe_interaction(
            "I just want to belong somewhere",
            {"label": "sad", "intensity": 0.6},
            {"score": 0.2},
            "You do belong.",
        )
        assert fresh_humanity.state.dominant_motivation == "connection"


class TestSeasonInference:
    def test_detects_winter(self, fresh_humanity):
        fresh_humanity.observe_interaction(
            "I feel withdrawn and everything is quiet and dark",
            {"label": "sad", "intensity": 0.3},
            {"score": 0.1},
            "Winter has its own wisdom.",
        )
        assert fresh_humanity.state.current_season == "winter"

    def test_detects_spring(self, fresh_humanity):
        fresh_humanity.observe_interaction(
            "There is new hope and possibility opening up",
            {"label": "curious", "intensity": 0.5},
            {"score": 0.1},
            "Spring arrives.",
        )
        assert fresh_humanity.state.current_season == "spring"


class TestTensionInference:
    def test_detects_vulnerability_vs_protection(self, fresh_humanity):
        fresh_humanity.observe_interaction(
            "I want to be open but I am afraid of getting hurt",
            {"label": "anxious", "intensity": 0.6},
            {"score": 0.4},
            "The wall and the bridge are the same material.",
        )
        assert fresh_humanity.state.active_tension == "vulnerability_vs_protection"


class TestPatternRecording:
    def test_records_self_doubt(self, fresh_humanity):
        fresh_humanity.observe_interaction(
            "I am probably not good enough for this",
            {"label": "sad", "intensity": 0.5},
            {"score": 0.2},
            "That voice is not the truth.",
        )
        patterns = fresh_humanity.get_patterns()
        assert any(p["pattern_name"] == "self_doubt" for p in patterns)

    def test_frequency_increments(self, fresh_humanity):
        for _ in range(3):
            fresh_humanity.observe_interaction(
                "I am not sure if I can do this",
                {"label": "anxious", "intensity": 0.4},
                {"score": 0.2},
                "Doubt is part of the process.",
            )
        patterns = fresh_humanity.get_patterns()
        p = next((x for x in patterns if x["pattern_name"] == "self_doubt"), None)
        assert p is not None
        assert p["frequency"] == 3


class TestContemplation:
    def test_returns_none_with_few_observations(self, fresh_humanity):
        assert fresh_humanity.contemplate() is None

    def test_generates_insight_with_enough_observations(self, fresh_humanity):
        for i in range(5):
            fresh_humanity.observe_interaction(
                f"Test input {i}",
                {"label": "curious", "intensity": 0.5},
                {"score": 0.1},
                "Response.",
            )
        insight = fresh_humanity.contemplate()
        assert insight is not None
        assert len(insight) > 10

    def test_insights_persist(self, fresh_humanity):
        for i in range(5):
            fresh_humanity.observe_interaction(f"Test {i}", {"label": "curious"}, {"score": 0.1}, "Ok.")
        fresh_humanity.contemplate()
        insights = fresh_humanity.get_insights()
        assert len(insights) > 0


class TestPromptFormatting:
    def test_format_includes_state(self, fresh_humanity):
        snippet = fresh_humanity.format_prompt_snippet()
        assert "UNDERSTANDING HUMAN NATURE" in snippet
        assert "seeker" in snippet
        assert "meaning" in snippet

    def test_format_includes_patterns(self, fresh_humanity):
        fresh_humanity.observe_interaction(
            "I am not sure about anything",
            {"label": "anxious", "intensity": 0.4},
            {"score": 0.2},
            "Uncertainty is human.",
        )
        snippet = fresh_humanity.format_prompt_snippet()
        assert "self doubt" in snippet.lower() or "patterns" in snippet.lower()


class TestCycle:
    def test_contemplation_chance(self, fresh_humanity):
        # Seed enough observations
        for i in range(5):
            fresh_humanity.observe_interaction(f"x{i}", {"label": "curious"}, {"score": 0.1}, "ok")
        class MockCtx:
            iteration = 15
            minutes_since_interaction = 0
        # With iteration % 15 == 0, contemplate has 30% chance
        # We just verify it doesn't crash
        fresh_humanity.cycle(MockCtx())
