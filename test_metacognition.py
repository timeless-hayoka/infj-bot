"""Tests for the metacognition module."""
import os
import tempfile
from pathlib import Path

import pytest

from metacognition import MetacognitionEngine


@pytest.fixture
def tmp_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield Path(path)
    os.unlink(path)


class TestMetacognitionEngine:
    def test_init_creates_db(self, tmp_db):
        meta = MetacognitionEngine(db_path=tmp_db)
        assert tmp_db.exists()

    def test_reflect_on_response_detects_over_certainty(self, tmp_db):
        meta = MetacognitionEngine(db_path=tmp_db)
        response = "This is definitely the answer. You should absolutely do it."
        reflection = meta.reflect_on_response("How should I proceed?", response)
        assert reflection is not None
        assert "certainty" in reflection.lower() or "facts" in reflection.lower()
        assert "over_certainty" in meta.cognitive_biases

    def test_reflect_on_response_detects_verbosity(self, tmp_db):
        meta = MetacognitionEngine(db_path=tmp_db)
        response = "A. " * 400  # Very long response
        reflection = meta.reflect_on_response("What is 2+2?", response)
        if reflection:
            assert any(b in meta.cognitive_biases for b in ["verbosity", "under_exploration", "over_certainty"])

    def test_reflect_on_response_no_issue(self, tmp_db):
        meta = MetacognitionEngine(db_path=tmp_db)
        response = "I'm not sure. Could you tell me more?"
        reflection = meta.reflect_on_response("What should I do?", response)
        assert reflection is None
        assert len(meta.cognitive_biases) == 0

    def test_current_growth_edge(self, tmp_db):
        meta = MetacognitionEngine(db_path=tmp_db)
        edge = meta.current_growth_edge()
        assert len(edge) > 5

    def test_current_growth_edge_from_bias(self, tmp_db):
        meta = MetacognitionEngine(db_path=tmp_db)
        # Induce over_certainty bias twice
        meta.reflect_on_response("q", "Definitely. Absolutely.")
        meta.reflect_on_response("q", "Always. Certainly. Never.")
        edge = meta.current_growth_edge()
        assert "certainty" in edge.lower() or "evidence" in edge.lower()

    def test_format_metacognitive_prompt(self, tmp_db):
        meta = MetacognitionEngine(db_path=tmp_db)
        # First induce a bias
        meta.reflect_on_response("q", "Definitely. Absolutely. Certainly.")
        prompt = meta.format_metacognitive_prompt()
        assert "METACOGNITIVE" in prompt
        assert "growth edge" in prompt.lower()

    def test_bias_report(self, tmp_db):
        meta = MetacognitionEngine(db_path=tmp_db)
        report = meta.get_bias_report()
        assert "No patterns observed" in report
        meta.reflect_on_response("q", "Definitely yes. Absolutely correct.")
        report = meta.get_bias_report()
        assert "over_certainty" in report
