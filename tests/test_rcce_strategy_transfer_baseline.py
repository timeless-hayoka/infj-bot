"""RCCE-1 baseline characterization: no unsupported cross-task transfer claims.

These tests use the actual production CognitiveControl and CognitiveLearningBridge,
not mocked decisions or invented model responses. They are not live-model trials.
"""
from drift.core.cognitive_control import CognitiveControl
from drift.core.cognitive_learning_bridge import CognitiveLearningBridge


def test_verified_training_failure_does_not_automatically_transfer():
    controller = CognitiveControl(failure_threshold=1)
    controller.observe("parser failure", "retry unchanged", outcome="failure", verified=True)
    assert controller.choose("parser failure", ["retry unchanged", "inspect cause"]).strategy == "inspect cause"
    # Different task ID: current controller does not generalize its learned decision.
    assert controller.choose("API schema failure", ["retry unchanged", "inspect cause"]).strategy == "retry unchanged"


def test_restart_preserves_training_decision_but_not_transfer(tmp_path):
    path = tmp_path / "rcce.sqlite"
    bridge = CognitiveLearningBridge(path, failure_threshold=1)
    assert bridge.record(
        "parser failure", "retry unchanged", "failure",
        verified=True, evidence="assertion: repeat attempt failed"
    )
    restarted = CognitiveLearningBridge(path, failure_threshold=1)
    assert restarted.choose("parser failure", ["retry unchanged", "inspect cause"]).strategy == "inspect cause"
    assert restarted.choose("API schema failure", ["retry unchanged", "inspect cause"]).strategy == "retry unchanged"


def test_unverified_feedback_cannot_change_transfer_decision(tmp_path):
    bridge = CognitiveLearningBridge(tmp_path / "unverified.sqlite", failure_threshold=1)
    assert bridge.record(
        "parser failure", "retry unchanged", "failure",
        verified=False, evidence="unsupported claim"
    ) is False
    assert bridge.choose("parser failure", ["retry unchanged", "inspect cause"]).strategy == "retry unchanged"
