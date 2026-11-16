import pytest
from drift.core.cognitive_control import CognitiveControl


def test_repeated_verified_failures_force_strategy_switch():
    control = CognitiveControl()
    for _ in range(3):
        control.observe("repair", "retry", outcome="failure", verified=True)
    assert control.choose("repair", ["retry", "inspect"]).strategy == "inspect"


def test_unverified_feedback_cannot_change_strategy():
    control = CognitiveControl()
    for _ in range(10):
        control.observe("repair", "retry", outcome="failure", verified=False)
    assert control.choose("repair", ["retry", "inspect"]).strategy == "retry"


def test_success_resets_consecutive_failures():
    control = CognitiveControl()
    for _ in range(2):
        control.observe("repair", "retry", outcome="failure", verified=True)
    control.observe("repair", "retry", outcome="success", verified=True)
    assert control.choose("repair", ["retry"]).strategy == "retry"


def test_exhaustion_does_not_repeat_blocked_action():
    control = CognitiveControl(failure_threshold=1)
    control.observe("repair", "retry", outcome="failure", verified=True)
    assert control.choose("repair", ["retry"]).strategy is None


def test_tasks_are_isolated():
    control = CognitiveControl(failure_threshold=1)
    control.observe("a", "retry", outcome="failure", verified=True)
    assert control.choose("b", ["retry"]).strategy == "retry"


def test_invalid_feedback_is_rejected():
    control = CognitiveControl()
    with pytest.raises(ValueError):
        control.observe("a", "b", outcome="maybe", verified=True)
