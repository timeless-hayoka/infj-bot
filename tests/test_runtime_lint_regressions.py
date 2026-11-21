from types import SimpleNamespace
from unittest.mock import Mock

from drift.core import dmu, psc_scaled
from drift.core.memory import DriftMemory
from drift.core.task_mutator import Task, TaskStatus, execute_mutation


def test_ranked_memory_keeps_ranked_results(monkeypatch):
    retriever = Mock()
    retriever.retrieve.return_value = [{"id": "memory-1", "content": "ranked result"}]
    monkeypatch.setattr(dmu, "DMURetriever", Mock(return_value=retriever))
    monkeypatch.setattr(psc_scaled, "get_psc_engine", Mock())
    memory = DriftMemory.__new__(DriftMemory)
    memory.embedding_function = Mock(return_value=[[0.5]])
    memory.unified_manager = SimpleNamespace(collection=object())
    memory.retrieve_context = Mock(return_value="fallback")

    assert memory.retrieve_context_ranked("test query") == "Memory: ranked result"
    memory.retrieve_context.assert_not_called()


def test_task_mutation_records_the_supplied_cycle():
    task = Task(task_id="test", title="Draft", intent_stability_history=[0.1])

    mutated, event, _ = execute_mutation(
        task=task,
        shadow_influence=0.4,
        current_mode="BALANCED",
        current_cycle=17,
    )

    assert mutated.status is TaskStatus.NEEDS_REFLECTION
    assert event.cycle == 17
    assert mutated.mutation_log[-1]["cycle"] == 17
