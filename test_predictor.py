"""Tests for the predictive needs model."""
import os
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from predictor import PredictiveNeeds


@pytest.fixture
def tmp_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield Path(path)
    os.unlink(path)


def _make_emotion(label: str, intensity: float) -> dict:
    return {"label": label, "intensity": intensity, "confidence": 0.8}


class TestPredictiveNeeds:
    def test_init_creates_db(self, tmp_db):
        p = PredictiveNeeds(db_path=tmp_db)
        assert tmp_db.exists()

    def test_record_interaction(self, tmp_db):
        p = PredictiveNeeds(db_path=tmp_db)
        p.record_interaction("I am stressed about work", _make_emotion("anxious", 0.7))
        patterns = p._load_recent_patterns(10)
        assert len(patterns) == 1
        assert patterns[0]["emotion_label"] == "anxious"
        assert patterns[0]["stress_score"] > 0

    def test_extract_topics(self, tmp_db):
        p = PredictiveNeeds(db_path=tmp_db)
        p.record_interaction("My partner and I are fighting about money", _make_emotion("sad", 0.5))
        patterns = p._load_recent_patterns(1)
        topics = patterns[0]["topics"].split(",")
        assert "relationship" in topics or "conflict" in topics or "security" in topics

    def test_time_of_day_analysis(self, tmp_db):
        p = PredictiveNeeds(db_path=tmp_db)
        # Simulate morning stress
        for _ in range(3):
            p.record_interaction("Morning anxiety about deadlines", _make_emotion("anxious", 0.6))
        patterns = p._load_recent_patterns(10)
        result = p._analyze_time_of_day(patterns)
        # The time bucket depends on when the test runs, so just check structure
        for bucket, data in result.items():
            assert "typical_emotion" in data
            assert "avg_stress" in data

    def test_predict_current_need_insufficient_data(self, tmp_db):
        p = PredictiveNeeds(db_path=tmp_db)
        assert p.predict_current_need() is None

    def test_predict_current_need_with_data(self, tmp_db):
        p = PredictiveNeeds(db_path=tmp_db)
        for i in range(8):
            p.record_interaction(f"I am stressed and overwhelmed at work {i}", _make_emotion("overwhelmed", 0.7))
        pred = p.predict_current_need()
        assert pred is not None
        assert "prediction" in pred
        assert "confidence" in pred
        assert 0.0 <= pred["confidence"] <= 1.0

    def test_detect_anomaly_emotion_shift(self, tmp_db):
        p = PredictiveNeeds(db_path=tmp_db)
        # Older patterns: calm
        for _ in range(5):
            p.record_interaction("All good", _make_emotion("neutral", 0.2))
        # Recent patterns: sad
        for _ in range(3):
            p.record_interaction("Feeling down", _make_emotion("sad", 0.6))
        anomaly = p.detect_anomaly()
        assert anomaly is not None
        assert anomaly["type"] == "emotion_shift"

    def test_detect_anomaly_stress_spike(self, tmp_db):
        p = PredictiveNeeds(db_path=tmp_db)
        # Same emotion but rising stress signals
        for _ in range(5):
            p.record_interaction("Normal day", _make_emotion("anxious", 0.2))
        for _ in range(3):
            p.record_interaction("PANIC everything is broken deadline urgent", _make_emotion("anxious", 0.9))
        anomaly = p.detect_anomaly()
        assert anomaly is not None
        assert anomaly["type"] == "stress_spike"

    def test_proactive_suggestion(self, tmp_db):
        p = PredictiveNeeds(db_path=tmp_db)
        for _ in range(6):
            p.record_interaction("I can't cope with this workload overwhelmed burned out", _make_emotion("overwhelmed", 0.8))
        # Also trigger an anomaly
        for _ in range(3):
            p.record_interaction("Actually things are okay", _make_emotion("neutral", 0.2))
        for _ in range(3):
            p.record_interaction("I am so sad and stressed", _make_emotion("sad", 0.8))
        suggestion = p.proactive_suggestion()
        assert suggestion is not None
        assert len(suggestion) > 10

    def test_format_predictive_prompt_empty(self, tmp_db):
        p = PredictiveNeeds(db_path=tmp_db)
        assert p.format_predictive_prompt() == ""

    def test_format_predictive_prompt_with_data(self, tmp_db):
        p = PredictiveNeeds(db_path=tmp_db)
        for _ in range(8):
            p.record_interaction("I am stressed and overwhelmed at work", _make_emotion("anxious", 0.7))
        prompt = p.format_predictive_prompt()
        assert "PREDICTIVE SENSE" in prompt
        assert "wonder" in prompt.lower()

    def test_gap_trend_stable(self, tmp_db):
        p = PredictiveNeeds(db_path=tmp_db)
        for i in range(6):
            p.record_interaction(f"msg {i}", _make_emotion("neutral", 0.3))
        trend = p._analyze_gap_trend(p._load_recent_patterns(10))
        assert trend in ("stable", None)

    def test_stress_signal_scoring(self, tmp_db):
        p = PredictiveNeeds(db_path=tmp_db)
        p.record_interaction("I am burned out and overwhelmed", _make_emotion("sad", 0.5))
        patterns = p._load_recent_patterns(1)
        assert patterns[0]["stress_score"] > 0.4
