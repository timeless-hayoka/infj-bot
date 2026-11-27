"""Stage 1: durable evidence and correction history, using real SQLite."""
import sqlite3

from drift.core.cognitive_learning_bridge import CognitiveLearningBridge


def test_verified_outcome_preserves_provenance_after_restart(tmp_path):
    db = tmp_path / "learning.db"
    bridge = CognitiveLearningBridge(db)
    assert bridge.record(
        "repair", "inspect", "success", verified=True,
        evidence="trace-001", source="test-runner", confidence=0.9,
        scope="session-a",
    )
    restarted = CognitiveLearningBridge(db)
    history = restarted.history("repair", scope="session-a")
    assert len(history) == 1
    assert history[0]["source"] == "test-runner"
    assert history[0]["confidence"] == 0.9
    assert history[0]["evidence"] == "trace-001"
    assert history[0]["scope"] == "session-a"


def test_correction_is_append_only_and_survives_restart(tmp_path):
    db = tmp_path / "learning.db"
    bridge = CognitiveLearningBridge(db)
    bridge.record("repair", "retry", "success", verified=True, evidence="trace-old")
    original = bridge.history("repair")[0]["id"]
    bridge.correct(original, "failure", evidence="trace-correction", source="reviewer")
    events = CognitiveLearningBridge(db).history("repair")
    assert len(events) == 2
    assert events[0]["outcome"] == "success"
    assert events[1]["outcome"] == "failure"
    assert events[1]["corrects_id"] == original
    assert events[1]["evidence"] == "trace-correction"


def test_unverified_correction_cannot_modify_history(tmp_path):
    db = tmp_path / "learning.db"
    bridge = CognitiveLearningBridge(db)
    bridge.record("repair", "retry", "success", verified=True, evidence="trace-old")
    original = bridge.history("repair")[0]["id"]
    import pytest
    with pytest.raises(ValueError):
        bridge.correct(original, "failure", evidence="", source="reviewer")
    assert len(CognitiveLearningBridge(db).history("repair")) == 1

def test_corrected_failure_controls_choice_after_restart(tmp_path):
    db = tmp_path / "learning.db"
    bridge = CognitiveLearningBridge(db, failure_threshold=1)
    bridge.record("repair", "retry", "success", verified=True, evidence="trace-old")
    original = bridge.history("repair")[0]["id"]
    bridge.correct(original, "failure", evidence="trace-new", source="reviewer")
    assert bridge.choose("repair", ["retry", "inspect"]).strategy == "inspect"
    restarted = CognitiveLearningBridge(db, failure_threshold=1)
    assert restarted.choose("repair", ["retry", "inspect"]).strategy == "inspect"
