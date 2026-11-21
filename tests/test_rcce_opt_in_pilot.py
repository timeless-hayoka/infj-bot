import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from drift.core.rcce_feedback import load_pilot_preference
from drift.interfaces import cli


@pytest.fixture
def feedback(tmp_path):
    path = tmp_path / "feedback.json"
    common = {"profile": "demo", "context": "planning"}
    rows = [
        {**common, "review": 1, "scope": "default", "preference": "cheap"},
        {**common, "review": 2, "scope": "urgent", "preference": "fast"},
        {**common, "review": 3, "scope": "urgent", "preference": "cheap"},
        {**common, "review": 4, "scope": "urgent", "retracts": 3},
    ]
    path.write_text(json.dumps(rows))
    return path


def test_loader_honors_corrections_and_context(feedback):
    assert "less total time" in load_pilot_preference(
        feedback, "demo", "planning", "urgent"
    )
    assert "lower total cost" in load_pilot_preference(
        feedback, "demo", "planning", "default"
    )
    with pytest.raises(ValueError, match="no applicable verified preference"):
        load_pilot_preference(feedback, "another", "planning", "urgent")


def test_loader_rejects_cross_scope_retraction(feedback):
    data = json.loads(feedback.read_text())
    data[-1]["retracts"] = 1
    feedback.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="same scope"):
        load_pilot_preference(feedback, "demo", "planning", "urgent")


def test_cli_requires_complete_opt_in(capsys):
    args = cli.build_parser().parse_args(["ask", "--rcce-profile", "demo", "Which?"])
    assert args.func(args) == 2
    assert "requires --rcce-feedback" in capsys.readouterr().err


def test_cli_wires_opt_in_and_preserves_normal_ask(feedback, monkeypatch):
    from drift.core import (
        being,
        brain,
        cognitive_orchestrator,
        commands,
        history,
        memory,
    )
    from drift.core import prompt_builder, unified_audit
    from drift.core.plugins import documents, goals

    provider = SimpleNamespace(agent_turn=Mock(return_value="B"), evaluate_last=Mock())
    memory_instance = SimpleNamespace(save_interaction=Mock())
    history_instance = SimpleNamespace(append=Mock())
    assemble = Mock(return_value=("built prompt", {"intensity": 0}, {"score": 0}))
    monkeypatch.setattr(brain, "DriftBrain", lambda: provider)
    monkeypatch.setattr(
        commands,
        "BotState",
        lambda **kwargs: SimpleNamespace(mode=kwargs["mode"], prefs={}),
    )
    monkeypatch.setattr(memory, "DriftMemory", lambda: memory_instance)
    monkeypatch.setattr(history, "ChatHistory", lambda: history_instance)
    monkeypatch.setattr(prompt_builder, "build_chat_prompt", assemble)
    monkeypatch.setattr(
        cognitive_orchestrator, "CognitiveOrchestrator", SimpleNamespace
    )
    monkeypatch.setattr(unified_audit, "wire_orchestrator_audit", Mock())
    monkeypatch.setattr(being, "get_being", SimpleNamespace)
    monkeypatch.setattr(documents, "DocumentStore", SimpleNamespace)
    monkeypatch.setattr(goals, "GoalsDB", SimpleNamespace)

    parser = cli.build_parser()
    original = feedback.read_bytes()
    opted_in = parser.parse_args(
        [
            "ask",
            "--rcce-feedback",
            str(feedback),
            "--rcce-profile",
            "demo",
            "--rcce-context",
            "planning",
            "--rcce-scope",
            "urgent",
            "Which?",
        ]
    )
    assert opted_in.func(opted_in) == 0
    assert "less total time" in provider.agent_turn.call_args.args[0]
    assert provider.agent_turn.call_args.kwargs == {
        "tools_enabled": False,
        "raw_user_input": "Which?",
    }
    assert assemble.call_args.kwargs["tools_enabled"] is False
    provider.evaluate_last.assert_not_called()
    memory_instance.save_interaction.assert_not_called()
    history_instance.append.assert_not_called()
    assert feedback.read_bytes() == original

    normal = parser.parse_args(["ask", "Which?"])
    assert normal.func(normal) == 0
    provider.agent_turn.assert_called_with(
        "built prompt", tools_enabled=True, raw_user_input="Which?"
    )
    provider.evaluate_last.assert_called_once()
    memory_instance.save_interaction.assert_called_once()
    history_instance.append.assert_called_once()
