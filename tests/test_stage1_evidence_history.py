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


def _legacy_database(path):
    # Actual pre-evidence schema; no invented provenance.
    with sqlite3.connect(path) as connection:
        connection.execute(
            """CREATE TABLE cognitive_outcomes (
            id INTEGER PRIMARY KEY, task TEXT NOT NULL, strategy TEXT NOT NULL,
            outcome TEXT NOT NULL CHECK(outcome IN ('success','failure')),
            scope TEXT NOT NULL DEFAULT 'global')"""
        )
        connection.execute(
            "INSERT INTO cognitive_outcomes(task,strategy,outcome) VALUES (?,?,?)",
            ("legacy-task", "retry", "failure"),
        )


def test_legacy_only_database_preserves_controller_decision(tmp_path):
    path = tmp_path / "legacy.db"
    _legacy_database(path)
    bridge = CognitiveLearningBridge(path, failure_threshold=1)
    assert bridge.choose("legacy-task", ["retry", "inspect"]).strategy == "inspect"


def test_mixed_schema_preserves_unrelated_legacy_outcome(tmp_path):
    path = tmp_path / "mixed.db"
    _legacy_database(path)
    bridge = CognitiveLearningBridge(path, failure_threshold=1)
    bridge.record("new-task", "scan", "success", verified=True, evidence="new-trace")
    assert bridge.choose("legacy-task", ["retry", "inspect"]).strategy == "inspect"
    restarted = CognitiveLearningBridge(path, failure_threshold=1)
    assert restarted.choose("legacy-task", ["retry", "inspect"]).strategy == "inspect"


def test_mixed_schema_preserves_legacy_outcome_after_correction(tmp_path):
    path = tmp_path / "mixed-corrected.db"
    _legacy_database(path)
    bridge = CognitiveLearningBridge(path, failure_threshold=1)
    bridge.record("new-task", "scan", "success", verified=True, evidence="new-trace")
    root = bridge.history("new-task")[0]["id"]
    bridge.correct(root, "failure", evidence="new-review", source="reviewer")
    assert bridge.choose("legacy-task", ["retry", "inspect"]).strategy == "inspect"
    restarted = CognitiveLearningBridge(path, failure_threshold=1)
    assert restarted.choose("legacy-task", ["retry", "inspect"]).strategy == "inspect"
    assert restarted.choose("new-task", ["scan", "inspect"]).strategy == "inspect"


def test_new_outcome_is_not_counted_twice_on_replay(tmp_path):
    path = tmp_path / "no-double-count.db"
    bridge = CognitiveLearningBridge(path, failure_threshold=2)
    bridge.record("repair", "retry", "failure", verified=True, evidence="one-failure")
    assert bridge.choose("repair", ["retry"]).strategy == "retry"
    assert CognitiveLearningBridge(path, failure_threshold=2).choose(
        "repair", ["retry"]
    ).strategy == "retry"


def test_chained_corrections_and_repeated_restarts(tmp_path):
    path = tmp_path / "chain.db"
    bridge = CognitiveLearningBridge(path, failure_threshold=1)
    bridge.record("repair", "retry", "success", verified=True, evidence="initial")
    root = bridge.history("repair")[0]["id"]
    first = bridge.correct(root, "failure", evidence="review-1", source="reviewer")
    assert bridge.choose("repair", ["retry", "inspect"]).strategy == "inspect"
    second = bridge.correct(first, "success", evidence="review-2", source="reviewer")
    expected_history = bridge.history("repair")
    assert [event["corrects_id"] for event in expected_history] == [None, root, first]
    assert expected_history[-1]["id"] == second
    for _ in range(3):
        reopened = CognitiveLearningBridge(path, failure_threshold=1)
        assert reopened.history("repair") == expected_history
        assert reopened.choose("repair", ["retry", "inspect"]).strategy == "retry"


def test_conflicting_sibling_corrections_cannot_both_be_effective(tmp_path):
    import pytest

    path = tmp_path / "conflict.db"
    bridge = CognitiveLearningBridge(path, failure_threshold=1)
    bridge.record("repair", "retry", "success", verified=True, evidence="initial")
    root = bridge.history("repair")[0]["id"]
    bridge.correct(root, "failure", evidence="review-1", source="reviewer-a")
    # Reject a stale correction target rather than silently counting both leaves.
    with pytest.raises(ValueError):
        bridge.correct(root, "success", evidence="review-2", source="reviewer-b")
    assert len(bridge.history("repair")) == 2
    assert CognitiveLearningBridge(path, failure_threshold=1).choose(
        "repair", ["retry", "inspect"]
    ).strategy == "inspect"


def test_corrected_decision_survives_separate_writer_and_reader_processes(tmp_path):
    import json
    import subprocess
    import sys

    path = tmp_path / "cross-process.db"
    writer = """
import json, os, sys
from drift.core.cognitive_learning_bridge import CognitiveLearningBridge
bridge = CognitiveLearningBridge(sys.argv[1], failure_threshold=1)
bridge.record("repair", "retry", "success", verified=True, evidence="initial")
root = bridge.history("repair")[0]["id"]
bridge.correct(root, "failure", evidence="review", source="independent-reviewer")
print(json.dumps({"pid": os.getpid(), "decision": bridge.choose("repair", ["retry", "inspect"]).strategy}))
"""
    reader = """
import json, os, sys
from drift.core.cognitive_learning_bridge import CognitiveLearningBridge
bridge = CognitiveLearningBridge(sys.argv[1], failure_threshold=1)
print(json.dumps({"pid": os.getpid(), "decision": bridge.choose("repair", ["retry", "inspect"]).strategy,
                  "history": bridge.history("repair")}))
"""
    written = json.loads(subprocess.check_output(
        [sys.executable, "-c", writer, str(path)], text=True, timeout=30
    ))
    read = json.loads(subprocess.check_output(
        [sys.executable, "-c", reader, str(path)], text=True, timeout=30
    ))
    assert written["pid"] != read["pid"]
    assert written["decision"] == read["decision"] == "inspect"
    assert [event["outcome"] for event in read["history"]] == ["success", "failure"]
    assert read["history"][1]["corrects_id"] == read["history"][0]["id"]


def test_replay_same_instance_is_idempotent(tmp_path):
    path = tmp_path / "replay.db"
    bridge = CognitiveLearningBridge(path, failure_threshold=2)
    bridge.record("repair", "retry", "failure", verified=True, evidence="single-failure")
    for _ in range(3):
        bridge._replay()
        assert bridge.choose("repair", ["retry"]).strategy == "retry"
    assert len(bridge.history("repair")) == 1


def test_mismatched_dual_write_history_fails_closed(tmp_path):
    import pytest

    path = tmp_path / "ambiguous.db"
    bridge = CognitiveLearningBridge(path)
    bridge.record("repair", "retry", "failure", verified=True, evidence="trace")
    # Simulate a pre-upgrade writer appending after the dual-write boundary.
    with sqlite3.connect(path) as connection:
        connection.execute(
            "INSERT INTO cognitive_outcomes(task,strategy,outcome) VALUES (?,?,?)",
            ("unexpected-old-writer", "retry", "success"),
        )
    with pytest.raises(ValueError, match="ambiguous legacy/evidence"):
        CognitiveLearningBridge(path)


def test_existing_forked_correction_history_fails_closed(tmp_path):
    import pytest

    path = tmp_path / "forked.db"
    bridge = CognitiveLearningBridge(path)
    bridge.record("repair", "retry", "success", verified=True, evidence="trace")
    root = bridge.history("repair")[0]["id"]
    bridge.correct(root, "failure", evidence="review-a", source="reviewer")
    # Reproduce a database created by the previous permissive correction code.
    with sqlite3.connect(path) as connection:
        connection.execute(
            "INSERT INTO cognitive_evidence(task,strategy,outcome,scope,evidence,source,"
            "confidence,corrects_id) VALUES (?,?,?,?,?,?,?,?)",
            ("repair", "retry", "success", "global", "review-b", "reviewer", 1.0, root),
        )
    with pytest.raises(ValueError, match="conflicting correction"):
        CognitiveLearningBridge(path)


def test_identical_legacy_and_new_outcomes_are_distinct_observations(tmp_path):
    path = tmp_path / "duplicate-values.db"
    _legacy_database(path)
    bridge = CognitiveLearningBridge(path, failure_threshold=2)
    bridge.record("legacy-task", "retry", "failure", verified=True, evidence="second-attempt")
    # Two distinct attempts have identical values; do not deduplicate by value.
    assert bridge.choose("legacy-task", ["retry", "inspect"]).strategy == "inspect"
    reopened = CognitiveLearningBridge(path, failure_threshold=2)
    assert reopened.choose("legacy-task", ["retry", "inspect"]).strategy == "inspect"
    root = reopened.history("legacy-task")[0]["id"]
    reopened.correct(root, "success", evidence="review", source="reviewer")
    assert reopened.choose("legacy-task", ["retry", "inspect"]).strategy == "retry"
    assert CognitiveLearningBridge(path, failure_threshold=2).choose(
        "legacy-task", ["retry", "inspect"]
    ).strategy == "retry"
    # Audit raw persisted rows separately from the bridge history projection.
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM cognitive_outcomes").fetchone() == (2,)
        assert connection.execute(
            "SELECT outcome,corrects_id FROM cognitive_evidence ORDER BY id"
        ).fetchall() == [("failure", None), ("success", root)]


def test_opt_in_orchestrator_correction_survives_process_restart(tmp_path):
    import json
    import os
    import secrets
    import subprocess
    import sys

    path = tmp_path / "orchestrator.db"
    env = dict(os.environ)
    env["DRIFT_OS_ROOT"] = str(tmp_path / "isolated-state")
    env["DRIFT_VAULT_PATH"] = str(tmp_path / "isolated-state" / "vault.jsonl")
    env["DRIFT_VAULT_SECRET"] = secrets.token_hex(32)
    writer = """
import json, os, sys
from drift.core.cognitive_orchestrator import CognitiveOrchestrator
orchestrator = CognitiveOrchestrator()
assert orchestrator.choose_cognitive_strategy("repair", ["retry", "inspect"]) is None
assert not orchestrator.record_cognitive_outcome("repair", "retry", "failure", verified=True, evidence="disabled")
bridge = orchestrator.enable_cognitive_learning(sys.argv[1])
assert not orchestrator.record_cognitive_outcome("repair", "retry", "failure", evidence="unverified")
assert not orchestrator.bus.get_recent("cognitive_outcome_verified")
for n in range(3):
    assert orchestrator.record_cognitive_outcome("repair", "retry", "failure", verified=True, evidence=f"trace-{n}")
assert orchestrator.choose_cognitive_strategy("repair", ["retry", "inspect"]).strategy == "inspect"
assert len(orchestrator.bus.get_recent("cognitive_outcome_verified")) == 3
root = bridge.history("repair")[-1]["id"]
bridge.correct(root, "success", evidence="review", source="reviewer")
print(json.dumps({"pid": os.getpid(), "decision": orchestrator.choose_cognitive_strategy("repair", ["retry", "inspect"]).strategy}))
"""
    reader = """
import json, os, sys
from drift.core.cognitive_orchestrator import CognitiveOrchestrator
orchestrator = CognitiveOrchestrator()
assert orchestrator.choose_cognitive_strategy("repair", ["retry", "inspect"]) is None
bridge = orchestrator.enable_cognitive_learning(sys.argv[1])
print(json.dumps({"pid": os.getpid(), "decision": orchestrator.choose_cognitive_strategy("repair", ["retry", "inspect"]).strategy,
                  "history": bridge.history("repair")}))
"""
    written = json.loads(subprocess.check_output(
        [sys.executable, "-c", writer, str(path)], env=env, text=True, timeout=30
    ).splitlines()[-1])
    read = json.loads(subprocess.check_output(
        [sys.executable, "-c", reader, str(path)], env=env, text=True, timeout=30
    ).splitlines()[-1])
    assert written["pid"] != read["pid"]
    assert written["decision"] == read["decision"] == "retry"
    assert len(read["history"]) == 4
    assert read["history"][-1]["corrects_id"] == read["history"][-2]["id"]
    assert read["history"][-1]["source"] == "reviewer"
