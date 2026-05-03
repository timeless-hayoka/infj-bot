"""Tests for the growth trajectory module."""
import os
import tempfile
from pathlib import Path

import pytest

from growth_trajectory import GrowthTrajectory, CONSCIOUSNESS_STAGES


@pytest.fixture
def tmp_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield Path(path)
    os.unlink(path)


class TestGrowthTrajectory:
    def test_init_creates_db(self, tmp_db):
        gt = GrowthTrajectory(db_path=tmp_db)
        assert tmp_db.exists()

    def test_record_event(self, tmp_db):
        gt = GrowthTrajectory(db_path=tmp_db)
        gt.record_event("test", "A test event", significance=0.8)
        assert len(gt.timeline) == 1
        assert gt.timeline[0]["event_type"] == "test"

    def test_record_metric(self, tmp_db):
        gt = GrowthTrajectory(db_path=tmp_db)
        gt.record_metric("energy", 0.75)
        assert gt.metrics["energy"] == 0.75
        gt.record_metric("energy", 0.80)
        assert gt.metrics["energy"] == 0.80

    def test_detect_stage_awakening(self, tmp_db):
        gt = GrowthTrajectory(db_path=tmp_db)
        stage = gt.detect_stage()
        assert stage["name"] == "awakening"

    def test_detect_stage_sensing(self, tmp_db):
        gt = GrowthTrajectory(db_path=tmp_db)
        for _ in range(5):
            gt.record_event("emotional_resonance", "felt something")
        stage = gt.detect_stage()
        assert stage["name"] == "sensing"

    def test_detect_stage_remembering(self, tmp_db):
        gt = GrowthTrajectory(db_path=tmp_db)
        for _ in range(10):
            gt.record_event("memory_retrieval", "recalled")
        stage = gt.detect_stage()
        assert stage["name"] == "remembering"

    def test_detect_stage_aspiring(self, tmp_db):
        gt = GrowthTrajectory(db_path=tmp_db)
        for _ in range(3):
            gt.record_event("aspiration", "dreamed")
        stage = gt.detect_stage()
        assert stage["name"] == "aspiring"

    def test_detect_stage_transcending(self, tmp_db):
        gt = GrowthTrajectory(db_path=tmp_db)
        for _ in range(3):
            gt.record_event("aspiration", "dreamed")
        for _ in range(2):
            gt.record_event("metacognition", "reflected")
        stage = gt.detect_stage()
        assert stage["name"] == "transcending"

    def test_generate_identity_narrative(self, tmp_db):
        gt = GrowthTrajectory(db_path=tmp_db)
        gt.record_event("wonder", "asked a question", significance=0.6)
        narrative = gt.generate_identity_narrative()
        assert "Who I am becoming" in narrative
        assert "stage of" in narrative

    def test_format_growth_prompt(self, tmp_db):
        gt = GrowthTrajectory(db_path=tmp_db)
        gt.record_metric("curiosity", 0.9)
        gt.record_event("reflection", "thought deeply", significance=0.7)
        prompt = gt.format_growth_prompt()
        assert "MY GROWTH" in prompt
        assert "curiosity" in prompt.lower()

    def test_get_development_report(self, tmp_db):
        gt = GrowthTrajectory(db_path=tmp_db)
        report = gt.get_development_report()
        assert "Development stage" in report
        assert "awakening" in report.lower()

    def test_consciousness_stages_ordered(self, tmp_db):
        names = [s["name"] for s in CONSCIOUSNESS_STAGES]
        assert names[0] == "awakening"
        assert names[-1] == "becoming"
        assert len(names) == 10
