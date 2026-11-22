"""Regression: task mutation must preserve the caller's cycle in its audit record."""

import pytest

from drift.core.task_mutator import Task, TaskStatus, execute_mutation


@pytest.mark.parametrize("mode", ["SECURITY", "BALANCED", "CONSERVATIVE"])
def test_mutation_records_current_cycle(mode):
    task = Task(task_id="cycle-test", title="Test task")
    updated, event, message = execute_mutation(
        task, shadow_influence=0.9, current_mode=mode, current_cycle=37
    )
    assert updated is task
    assert event is not None, message
    assert event.cycle == 37
    assert task.mutation_log[-1]["cycle"] == 37


def test_mutation_gate_does_not_write_audit_record():
    task = Task(task_id="held", title="Held task")
    updated, event, message = execute_mutation(
        task, shadow_influence=0.0, current_mode="SECURITY", current_cycle=41
    )
    assert updated is task
    assert event is None
    assert task.status is TaskStatus.OPEN
    assert task.mutation_log == []
    assert "GATE HELD" in message
