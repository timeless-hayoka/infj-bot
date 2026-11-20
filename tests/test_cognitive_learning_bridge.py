from drift.core.cognitive_learning_bridge import CognitiveLearningBridge


def test_verified_failures_survive_restart(tmp_path):
    path = tmp_path / "learning.db"
    bridge = CognitiveLearningBridge(path)
    for i in range(3):
        assert bridge.record(
            "repair", "retry", "failure", verified=True, evidence=f"trace-{i}"
        )
    restarted = CognitiveLearningBridge(path)
    assert restarted.choose("repair", ["retry", "inspect"]).strategy == "inspect"


def test_unverified_outcomes_are_not_persisted(tmp_path):
    path = tmp_path / "learning.db"
    bridge = CognitiveLearningBridge(path, failure_threshold=1)
    assert not bridge.record(
        "repair", "retry", "failure", verified=False, evidence="claim"
    )
    assert (
        CognitiveLearningBridge(path, failure_threshold=1)
        .choose("repair", ["retry"])
        .strategy
        == "retry"
    )


def test_verified_outcomes_require_evidence(tmp_path):
    import pytest

    bridge = CognitiveLearningBridge(tmp_path / "learning.db")
    with pytest.raises(ValueError):
        bridge.record("repair", "retry", "success", verified=True, evidence="")
