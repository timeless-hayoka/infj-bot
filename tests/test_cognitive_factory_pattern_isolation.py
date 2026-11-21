"""Regression: cognitive factories must not share mutable proposal templates."""

from drift.core.cognitive_factory import CognitiveFactory


def test_pattern_mutation_isolated_between_factory_instances(tmp_path):
    first = CognitiveFactory(str(tmp_path / "first.db"))
    second = CognitiveFactory(str(tmp_path / "second.db"))
    original = second.NEED_PATTERNS[0]["methods"][:]
    first.NEED_PATTERNS[0]["methods"].append("injected_method")
    assert second.NEED_PATTERNS[0]["methods"] == original


def test_pattern_mutation_does_not_affect_new_factory(tmp_path):
    first = CognitiveFactory(str(tmp_path / "first.db"))
    first.NEED_PATTERNS[0]["keyword"] = "unexpected_keyword"
    fresh = CognitiveFactory(str(tmp_path / "fresh.db"))
    assert fresh.NEED_PATTERNS[0]["keyword"] == "gratitude"


def test_nested_method_list_mutation_does_not_leak_to_new_instance(tmp_path):
    first = CognitiveFactory(str(tmp_path / "first.db"))
    first.NEED_PATTERNS[0]["methods"][0] = "corrupted"
    fresh = CognitiveFactory(str(tmp_path / "fresh.db"))
    assert fresh.NEED_PATTERNS[0]["methods"][0] == "record_gratitude"


def test_separate_factory_databases_preserve_independent_proposals(tmp_path):
    first = CognitiveFactory(str(tmp_path / "first.db"))
    second = CognitiveFactory(str(tmp_path / "second.db"))
    proposal = first.propose("I want a gratitude practice")
    assert proposal is not None
    assert proposal.name == "gratitude_journal"
    assert [item.name for item in first.list_pending_proposals()] == ["gratitude_journal"]
    assert second.list_pending_proposals() == []
