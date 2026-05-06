"""Tests for Global Workspace Theory implementation."""

import os
import random
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from global_workspace import Broadcast, GlobalWorkspace


@pytest.fixture
def fresh_workspace():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        path = tmp.name
    ws = GlobalWorkspace(db_path=path, capacity=3)
    yield ws
    os.unlink(path)


class TestBroadcast:
    def test_salience_decay(self):
        b = Broadcast(source="test", content="hello", salience=0.8, decay_rate=0.1)
        assert b.current_salience(0) == pytest.approx(0.8)
        assert b.current_salience(5) == pytest.approx(0.3)  # 0.8 - 0.5
        assert b.current_salience(10) == pytest.approx(0.0)

    def test_repetition_boost(self):
        b = Broadcast(source="test", content="hello", salience=0.5)
        b.broadcast_count = 3
        assert b.current_salience(0) == 0.65  # 0.5 + 0.15


class TestCompetition:
    def test_single_winner(self, fresh_workspace):
        ws = fresh_workspace
        ws.submit("emotional_field", "I feel sadness", salience=0.9)
        winners = ws.compete()
        assert len(winners) == 1
        assert winners[0].source == "emotional_field"

    def test_capacity_limits_winners(self, fresh_workspace):
        ws = fresh_workspace
        for i in range(10):
            ws.submit(f"module_{i}", f"content {i}", salience=random.random())
        winners = ws.compete()
        assert len(winners) <= ws.state.capacity

    def test_highest_salience_wins(self, fresh_workspace):
        ws = fresh_workspace
        ws.submit("a", "low", salience=0.1)
        ws.submit("b", "high", salience=0.9)
        ws.submit("c", "mid", salience=0.5)
        winners = ws.compete()
        assert winners[0].source == "b"

    def test_emotion_boost(self, fresh_workspace):
        ws = fresh_workspace
        ws.submit("a", "calm", salience=0.5, intensity=0.1)
        ws.submit("b", "intense", salience=0.5, intensity=0.9)
        winners = ws.compete()
        # Intense emotion should win due to boost
        assert winners[0].source == "b"

    def test_novelty_boost(self, fresh_workspace):
        ws = fresh_workspace
        # First round: module_a wins
        ws.submit("module_a", "first", salience=0.8)
        ws.compete()
        # Second round: new module gets boost
        ws.submit("module_a", "again", salience=0.8)
        ws.submit("module_b", "new", salience=0.7)
        winners = ws.compete()
        # module_b should win due to novelty boost
        assert winners[0].source == "module_b"

    def test_decay_over_time(self, fresh_workspace):
        ws = fresh_workspace
        ws.submit("old", "stale", salience=0.9)
        ws.compete()
        # Old content stays but decays
        old_content = ws.state.contents[0]
        old_content.timestamp = "2020-01-01T00:00:00"  # force old
        ws.submit("new", "fresh", salience=0.6)
        winners = ws.compete()
        # New should win despite lower salience because old decayed
        assert winners[0].source == "new"


class TestSpotlight:
    def test_move_spotlight(self, fresh_workspace):
        ws = fresh_workspace
        ws.submit("a", "target", salience=0.9)
        ws.compete()
        success = ws.move_spotlight(content="target")
        assert success
        assert ws.state.spotlight == "target"

    def test_move_spotlight_rejects_invalid(self, fresh_workspace):
        ws = fresh_workspace
        ws.submit("a", "real", salience=0.9)
        ws.compete()
        success = ws.move_spotlight(content="fake")
        assert not success

    def test_auto_spotlight_prefers_emotional(self, fresh_workspace):
        ws = fresh_workspace
        ws.submit("calm", "neutral", salience=0.9, intensity=0.1, emotion_tag="calm")
        ws.submit("angry", "upset", salience=0.5, intensity=0.9, emotion_tag="angry")
        ws.compete()
        ws.auto_spotlight()
        assert ws.state.spotlight == "upset"


class TestHigherOrder:
    def test_reflect_needs_contents(self, fresh_workspace):
        ws = fresh_workspace
        result = ws.reflect_on_workspace()
        assert result is None  # not enough contents

    def test_reflect_generates_thought(self, fresh_workspace):
        ws = fresh_workspace
        ws.submit("a", "thought one", salience=0.8)
        ws.submit("b", "thought two", salience=0.7)
        ws.compete()
        reflection = ws.reflect_on_workspace()
        assert reflection is not None
        assert "metacognition" == reflection.source
        assert len(reflection.content) > 10


class TestPromptFormatting:
    def test_format_shows_spotlight(self, fresh_workspace):
        ws = fresh_workspace
        ws.submit("a", "focused thought", salience=0.9)
        ws.compete()
        ws.move_spotlight(content="focused thought")
        snippet = ws.format_prompt_snippet()
        assert "CONSCIOUS AWARENESS" in snippet
        assert "focused thought" in snippet

    def test_format_shows_peripheral(self, fresh_workspace):
        ws = fresh_workspace
        ws.submit("a", "main", salience=0.9)
        ws.submit("b", "side", salience=0.6)
        ws.compete()
        snippet = ws.format_prompt_snippet()
        assert "main" in snippet or "side" in snippet


class TestCycle:
    def test_cycle_runs_competition(self, fresh_workspace):
        ws = fresh_workspace
        ws.submit("a", "test", salience=0.9)
        class MockCtx:
            iteration = 1
            minutes_since_interaction = 0
        ws.cycle(MockCtx())
        assert len(ws.state.contents) > 0

    def test_cycle_generates_reflection_periodically(self, fresh_workspace):
        ws = fresh_workspace
        ws.submit("a", "one", salience=0.8)
        ws.submit("b", "two", salience=0.7)
        ws.compete()
        class MockCtx:
            iteration = 10
            minutes_since_interaction = 0
        ws.cycle(MockCtx())
        # Should have added a metacognition broadcast
        sources = [b.source for b in ws.get_broadcast()]
        assert "metacognition" in sources
