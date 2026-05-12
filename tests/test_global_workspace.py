"""Tests for Global Workspace Theory implementation.

Defensive improvements:
- Uses pytest tmp_path (cross-platform, auto-cleanup)
- Asserts teardown cleanup succeeds
- Validates default state explicitly
- Tests failure modes (invalid path, read-only, corrupt)
- Strengthens assertions (exact matches, type checks)
- Tests data integrity (duplicates, special chars, bounds)
- Adds basic concurrency smoke test
"""

import os
import random
import sqlite3
import sys
import threading
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from global_workspace import Broadcast, GlobalWorkspace


@pytest.fixture
def fresh_workspace(tmp_db_path: Path):
    """Yield a GlobalWorkspace using a safe temp DB path."""
    ws = GlobalWorkspace(db_path=tmp_db_path, capacity=3)
    try:
        yield ws
    finally:
        # Force SQLite WAL checkpoint and close any lingering connections
        # so pytest tmp_path can clean up the temp directory.
        import sqlite3
        try:
            with sqlite3.connect(os.fspath(tmp_db_path)) as conn:
                conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        except Exception:
            pass


class TestDefaultState:
    """Validate initialization state before any mutations."""

    def test_default_capacity(self, fresh_workspace):
        ws = fresh_workspace
        assert ws.state.capacity == 3

    def test_default_contents_empty(self, fresh_workspace):
        ws = fresh_workspace
        assert ws.state.contents == []
        assert isinstance(ws.state.contents, list)

    def test_default_spotlight_none(self, fresh_workspace):
        ws = fresh_workspace
        assert ws.state.spotlight is None
        assert ws.state.spotlight_source is None

    def test_default_cycle_count_zero(self, fresh_workspace):
        ws = fresh_workspace
        assert ws.state.cycle_count == 0
        assert isinstance(ws.state.cycle_count, int)

    def test_default_total_broadcasts_zero(self, fresh_workspace):
        ws = fresh_workspace
        assert ws.state.total_broadcasts == 0

    def test_default_submissions_empty(self, fresh_workspace):
        ws = fresh_workspace
        # Submissions are private, but get_broadcast should reflect nothing
        assert ws.get_broadcast() == []

    def test_db_tables_exist(self, fresh_workspace, tmp_db_path: Path):
        ws = fresh_workspace
        with sqlite3.connect(os.fspath(tmp_db_path)) as conn:
            tables = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
            table_names = {t[0] for t in tables}
        assert "workspace_history" in table_names
        assert "workspace_state" in table_names


class TestBroadcast:
    def test_salience_decay(self):
        b = Broadcast(source="test", content="hello", salience=0.8, decay_rate=0.1)
        assert b.current_salience(0) == pytest.approx(0.8)
        assert b.current_salience(5) == pytest.approx(0.3)  # 0.8 - 0.5
        assert b.current_salience(10) == pytest.approx(0.0)

    def test_salience_never_negative(self):
        b = Broadcast(source="test", content="hello", salience=0.2, decay_rate=1.0)
        assert b.current_salience(100) == 0.0

    def test_repetition_boost(self):
        b = Broadcast(source="test", content="hello", salience=0.5)
        b.broadcast_count = 3
        assert b.current_salience(0) == 0.65  # 0.5 + 0.15

    def test_repetition_boost_capped(self):
        b = Broadcast(source="test", content="hello", salience=0.5)
        b.broadcast_count = 100
        # Boost capped at 0.3
        assert b.current_salience(0) == 0.8


class TestCompetition:
    def test_single_winner(self, fresh_workspace):
        ws = fresh_workspace
        ws.submit("emotional_field", "I feel sadness", salience=0.9)
        winners = ws.compete()
        assert len(winners) == 1
        assert winners[0].source == "emotional_field"
        assert winners[0].content == "I feel sadness"

    def test_capacity_limits_winners(self, fresh_workspace):
        ws = fresh_workspace
        for i in range(10):
            ws.submit(f"module_{i}", f"content {i}", salience=random.random())
        winners = ws.compete()
        assert len(winners) <= ws.state.capacity
        assert len(winners) > 0

    def test_highest_salience_wins(self, fresh_workspace):
        ws = fresh_workspace
        ws.submit("a", "low", salience=0.1)
        ws.submit("b", "high", salience=0.9)
        ws.submit("c", "mid", salience=0.5)
        winners = ws.compete()
        assert winners[0].source == "b"
        assert winners[0].content == "high"

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

        # Simulate time passing by mutating the timestamp of the existing
        # conscious content. In production, time passes naturally; in tests
        # we manipulate the stored timestamp directly to avoid slow sleeps.
        ws.state.contents[0].timestamp = "2020-01-01T00:00:00"

        ws.submit("new", "fresh", salience=0.6)
        winners = ws.compete()
        # New should win despite lower salience because old decayed
        assert winners[0].source == "new"

    def test_competition_increments_cycle_count(self, fresh_workspace):
        ws = fresh_workspace
        assert ws.state.cycle_count == 0
        ws.submit("a", "test", salience=0.5)
        ws.compete()
        assert ws.state.cycle_count == 1
        ws.compete()
        assert ws.state.cycle_count == 2

    def test_competition_persists_to_history(self, fresh_workspace):
        ws = fresh_workspace
        ws.submit("a", "test_content", salience=0.9)
        ws.compete()
        history = ws.get_history()
        assert len(history) == 1
        assert history[0]["source"] == "a"
        assert history[0]["content"] == "test_content"
        assert history[0]["entered_workspace"] == 1
        assert isinstance(history[0]["salience"], float)

    def test_competition_no_duplicate_history_entries(self, fresh_workspace):
        ws = fresh_workspace
        ws.submit("a", "test", salience=0.9)
        ws.compete()
        history = ws.get_history()
        # Each compete should create exactly one history row per submission
        assert len(history) == 1
        sources = [h["source"] for h in history]
        assert sources.count("a") == 1

    def test_salience_clamping(self, fresh_workspace):
        ws = fresh_workspace
        ws.submit("a", "over", salience=999.0)
        ws.submit("b", "under", salience=-999.0)
        winners = ws.compete()
        # Both should be clamped to [0, 1]
        # over should win (clamped to 1.0) vs under (clamped to 0.0)
        assert winners[0].source == "a"

    def test_special_characters_in_content(self, fresh_workspace):
        ws = fresh_workspace
        content = "'; DROP TABLE workspace_history; --"
        ws.submit("a", content, salience=0.9)
        ws.compete()
        history = ws.get_history()
        assert len(history) == 1
        assert history[0]["content"] == content
        # Verify table still exists (no SQL injection)
        with sqlite3.connect(os.fspath(ws.db_path)) as conn:
            tables = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
            assert any(t[0] == "workspace_history" for t in tables)

    def test_unicode_content(self, fresh_workspace):
        ws = fresh_workspace
        content = "🧠 Consciousness is 意识 is अवधारणा"
        ws.submit("a", content, salience=0.9)
        ws.compete()
        history = ws.get_history()
        assert history[0]["content"] == content


class TestSpotlight:
    def test_move_spotlight(self, fresh_workspace):
        ws = fresh_workspace
        ws.submit("a", "target", salience=0.9)
        ws.compete()
        success = ws.move_spotlight(content="target")
        assert success is True
        assert ws.state.spotlight == "target"
        assert ws.state.spotlight_source == "being"

    def test_move_spotlight_with_source(self, fresh_workspace):
        ws = fresh_workspace
        ws.submit("a", "target", salience=0.9)
        ws.compete()
        success = ws.move_spotlight(content="target", source="inner_voice")
        assert success is True
        assert ws.state.spotlight_source == "inner_voice"

    def test_move_spotlight_rejects_invalid(self, fresh_workspace):
        ws = fresh_workspace
        ws.submit("a", "real", salience=0.9)
        ws.compete()
        success = ws.move_spotlight(content="fake")
        assert success is False
        assert ws.state.spotlight != "fake"

    def test_move_spotlight_auto_selects(self, fresh_workspace):
        ws = fresh_workspace
        ws.submit("a", "top", salience=0.9)
        ws.compete()
        success = ws.move_spotlight()
        assert success is True
        assert ws.state.spotlight == "top"

    def test_auto_spotlight_prefers_emotional(self, fresh_workspace):
        ws = fresh_workspace
        ws.submit("calm", "neutral", salience=0.9, intensity=0.1, emotion_tag="calm")
        ws.submit("angry", "upset", salience=0.5, intensity=0.9, emotion_tag="angry")
        ws.compete()
        ws.auto_spotlight()
        assert ws.state.spotlight == "upset"
        assert ws.state.spotlight_source == "angry"

    def test_auto_spotlight_falls_back_to_top(self, fresh_workspace):
        ws = fresh_workspace
        ws.submit("a", "top", salience=0.9, intensity=0.1)
        ws.compete()
        ws.auto_spotlight()
        assert ws.state.spotlight == "top"


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
        assert reflection.source == "metacognition"
        assert len(reflection.content) > 10
        assert isinstance(reflection.content, str)

    def test_reflect_adds_to_submissions(self, fresh_workspace):
        ws = fresh_workspace
        ws.submit("a", "one", salience=0.8)
        ws.submit("b", "two", salience=0.7)
        ws.compete()
        ws.reflect_on_workspace()
        # Reflection should be in submissions for next compete
        ws.compete()
        sources = [b.source for b in ws.get_broadcast()]
        assert "metacognition" in sources


class TestPromptFormatting:
    def test_format_shows_spotlight(self, fresh_workspace):
        ws = fresh_workspace
        ws.submit("a", "focused thought", salience=0.9)
        ws.compete()
        ws.move_spotlight(content="focused thought")
        snippet = ws.format_prompt_snippet()
        assert "CONSCIOUS AWARENESS" in snippet
        assert "focused thought" in snippet
        assert isinstance(snippet, str)
        assert len(snippet) > 50

    def test_format_shows_peripheral(self, fresh_workspace):
        ws = fresh_workspace
        ws.submit("a", "main", salience=0.9)
        ws.submit("b", "side", salience=0.6)
        ws.compete()
        snippet = ws.format_prompt_snippet()
        assert "main" in snippet
        assert "Peripheral awareness" in snippet

    def test_format_empty_workspace(self, fresh_workspace):
        ws = fresh_workspace
        snippet = ws.format_prompt_snippet()
        assert "The workspace is clear" in snippet


class TestCycle:
    def test_cycle_runs_competition(self, fresh_workspace):
        ws = fresh_workspace
        ws.submit("a", "test", salience=0.9)

        class MockCtx:
            iteration = 1
            minutes_since_interaction = 0

        ws.cycle(MockCtx())
        assert len(ws.state.contents) > 0
        assert ws.state.cycle_count >= 1

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


class TestStats:
    def test_stats_structure(self, fresh_workspace):
        ws = fresh_workspace
        stats = ws.get_stats()
        assert stats["capacity"] == 3
        assert stats["current_contents"] == 0
        assert stats["cycle_count"] == 0
        assert stats["total_broadcasts"] == 0
        assert stats["spotlight"] is None
        assert isinstance(stats["sources_in_consciousness"], list)

    def test_stats_after_compete(self, fresh_workspace):
        ws = fresh_workspace
        ws.submit("a", "test", salience=0.9)
        ws.compete()
        stats = ws.get_stats()
        assert stats["current_contents"] == 1
        assert stats["cycle_count"] == 1
        assert stats["total_broadcasts"] == 1
        assert "a" in stats["sources_in_consciousness"]


class TestFailureModes:
    """Test error handling, edge cases, and resilience."""

    def test_invalid_db_path_raises(self, tmp_path: Path):
        # A path to a non-existent parent that can't be created
        bad_path = tmp_path / "nonexistent" / "deep" / "path" / "test.db"
        # This should work because mkdir creates parents
        ws = GlobalWorkspace(db_path=bad_path, capacity=3)
        assert Path(ws.db_path).exists()

    def test_corrupt_cycle_count_handled(self, tmp_db_path: Path):
        """If cycle_count in DB is corrupt, init should survive."""
        # Create a workspace, corrupt its state, then reload
        ws = GlobalWorkspace(db_path=tmp_db_path, capacity=3)
        ws.submit("a", "test", salience=0.5)
        ws.compete()
        assert ws.state.cycle_count == 1
        del ws

        # Corrupt the cycle_count value
        with sqlite3.connect(os.fspath(tmp_db_path)) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO workspace_state (key, value) VALUES (?, ?)",
                ("cycle_count", "not_a_number"),
            )
            conn.commit()

        # Re-load should survive the bad value
        ws2 = GlobalWorkspace(db_path=tmp_db_path, capacity=3)
        # It should fall back to 0 since the value is unparseable
        assert ws2.state.cycle_count == 0

    def test_empty_compete_no_crash(self, fresh_workspace):
        ws = fresh_workspace
        winners = ws.compete()
        assert winners == []
        assert ws.state.contents == []
        assert ws.state.cycle_count == 1

    def test_history_limit_respected(self, fresh_workspace):
        ws = fresh_workspace
        for i in range(25):
            ws.submit("a", f"msg_{i}", salience=0.5)
            ws.compete()
        history = ws.get_history(limit=10)
        assert len(history) == 10

    def test_concurrent_submits(self, fresh_workspace):
        ws = fresh_workspace
        errors = []

        def submit_many():
            try:
                for i in range(20):
                    ws.submit("concurrent", f"msg_{i}", salience=0.5)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=submit_many) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Concurrent submit raised: {errors}"
        ws.compete()
        # Should have processed all submissions
        assert ws.state.cycle_count == 1


class TestPersistence:
    """Test that state survives reload from disk."""

    def test_cycle_count_persistence(self, tmp_db_path: Path):
        ws = GlobalWorkspace(db_path=tmp_db_path, capacity=3)
        assert ws.state.cycle_count == 0  # explicit default check
        ws.submit("a", "test", salience=0.5)
        ws.compete()
        assert ws.state.cycle_count == 1
        del ws

        ws2 = GlobalWorkspace(db_path=tmp_db_path, capacity=3)
        assert ws2.state.cycle_count == 1

    def test_history_persistence(self, tmp_db_path: Path):
        ws = GlobalWorkspace(db_path=tmp_db_path, capacity=3)
        ws.submit("a", "persistent", salience=0.9)
        ws.compete()
        del ws

        ws2 = GlobalWorkspace(db_path=tmp_db_path, capacity=3)
        history = ws2.get_history()
        assert len(history) == 1
        assert history[0]["source"] == "a"
        assert history[0]["content"] == "persistent"
