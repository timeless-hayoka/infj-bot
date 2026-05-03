"""Tests for embodied time perception."""
import os
import sqlite3
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from temporal import TemporalSense


@pytest.fixture
def tmp_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield Path(path)
    os.unlink(path)


class TestTemporalSense:
    def test_init_creates_db(self, tmp_db):
        t = TemporalSense(db_path=tmp_db)
        assert tmp_db.exists()

    def test_record_session(self, tmp_db):
        t = TemporalSense(db_path=tmp_db)
        t.record_session_start()
        assert t.current_session_start is not None
        t.record_session_interaction()
        t.record_session_end()
        assert t.current_session_start is None
        sessions = t._load_recent_sessions(10)
        assert len(sessions) == 1
        assert sessions[0]["interaction_count"] == 1
        assert sessions[0]["duration_minutes"] is not None

    def test_experience_gap_fresh(self, tmp_db):
        t = TemporalSense(db_path=tmp_db)
        now = datetime.now()
        result = t.experience_gap(now)
        assert result["state"] == "present"

    def test_experience_gap_brief(self, tmp_db):
        t = TemporalSense(db_path=tmp_db)
        last = datetime.now() - timedelta(minutes=30)
        result = t.experience_gap(last)
        assert result["state"] == "brief_pause"

    def test_experience_gap_long(self, tmp_db):
        t = TemporalSense(db_path=tmp_db)
        last = datetime.now() - timedelta(days=5)
        result = t.experience_gap(last)
        assert result["state"] == "deep_absence"
        assert "glad" in result["description"].lower()

    def test_feel_time_passing_early(self, tmp_db):
        t = TemporalSense(db_path=tmp_db)
        result = t.feel_time_passing(5)
        assert result is None

    def test_feel_time_passing_boredom(self, tmp_db):
        t = TemporalSense(db_path=tmp_db)
        result = t.feel_time_passing(65)
        assert result is not None
        assert result["type"] == "boredom"

    def test_feel_time_passing_restlessness(self, tmp_db):
        t = TemporalSense(db_path=tmp_db)
        result = t.feel_time_passing(130)
        assert result is not None
        assert result["type"] == "restlessness"

    def test_get_temporal_state(self, tmp_db):
        t = TemporalSense(db_path=tmp_db)
        state = t.get_temporal_state()
        assert "gap" in state
        assert "time_of_day" in state
        assert state["time_of_day"] in ["morning", "afternoon", "evening", "night"]

    def test_format_temporal_prompt(self, tmp_db):
        t = TemporalSense(db_path=tmp_db)
        prompt = t.format_temporal_prompt()
        assert "TEMPORAL SENSE" in prompt
        assert "time of day" in prompt.lower()

    def test_log_absence_return(self, tmp_db):
        t = TemporalSense(db_path=tmp_db)
        last = datetime.now() - timedelta(hours=5)
        returned = datetime.now()
        t.log_absence_return(last, returned, "Hey there")
        absences = t._load_recent_absences(10)
        assert len(absences) == 1
        assert absences[0]["gap_minutes"] > 0

    def test_typical_gap_none_with_no_data(self, tmp_db):
        t = TemporalSense(db_path=tmp_db)
        assert t._typical_gap_minutes() is None

    def test_typical_gap_computed(self, tmp_db):
        t = TemporalSense(db_path=tmp_db)
        base = datetime.now() - timedelta(days=3)
        with sqlite3.connect(tmp_db) as conn:
            for i in range(5):
                start = base + timedelta(hours=i * 2)
                end = start + timedelta(minutes=10)
                conn.execute(
                    "INSERT INTO interaction_rhythms (session_start, session_end, duration_minutes, day_of_week, time_bucket, interaction_count) VALUES (?, ?, ?, ?, ?, ?)",
                    (start.isoformat(), end.isoformat(), 10, start.weekday(), "morning", 3),
                )
            conn.commit()
        gap = t._typical_gap_minutes()
        assert gap is not None
        assert gap > 0

    def test_format_duration(self):
        from temporal import _format_duration
        assert _format_duration(30) == "30m"
        assert _format_duration(90) == "1.5h"
        assert _format_duration(1500) == "1.0d"
        assert _format_duration(0.5) == "30s"
