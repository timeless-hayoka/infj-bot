"""Tests for the cognitive factory — proposal, generation, validation, installation."""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from cognitive_architecture import CognitiveArchitecture
from cognitive_factory import AbilityProposal, CognitiveFactory


@pytest.fixture
def fresh_factory():
    CognitiveArchitecture.reset_instance()
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        path = tmp.name
    factory = CognitiveFactory(db_path=path)
    yield factory
    CognitiveArchitecture.reset_instance()
    os.unlink(path)


class TestProposals:
    def test_propose_matching_need(self, fresh_factory):
        proposal = fresh_factory.propose("I think the bot should track gratitude")
        assert proposal is not None
        assert proposal.name == "gratitude_journal"
        assert "gratitude" in proposal.observed_need.lower()

    def test_propose_no_match(self, fresh_factory):
        proposal = fresh_factory.propose("something completely unrelated xyz")
        assert proposal is None

    def test_pending_persistence(self, fresh_factory):
        fresh_factory.propose("humor would be nice")
        pending = fresh_factory.list_pending_proposals()
        assert len(pending) == 1
        assert pending[0].name == "humor_sense"

    def test_summarize_pending(self, fresh_factory):
        fresh_factory.propose("celebration of wins")
        text = fresh_factory.summarize_pending()
        assert "celebration_engine" in text
        assert "wins" in text

    def test_summarize_empty(self, fresh_factory):
        text = fresh_factory.summarize_pending()
        assert "No pending" in text


class TestCodeGeneration:
    def test_generate_module_structure(self, fresh_factory):
        proposal = fresh_factory.propose("storytelling")
        source = fresh_factory.generate_module(proposal)
        assert "class Storyteller:" in source
        assert "def _register():" in source
        assert "storyteller" in source
        assert proposal.purpose in source

    def test_generated_module_has_custom_methods(self, fresh_factory):
        proposal = fresh_factory.propose("gratitude")
        source = fresh_factory.generate_module(proposal)
        for method in proposal.proposed_methods:
            assert f"def {method}(self)" in source


class TestValidation:
    def test_valid_module_passes(self, fresh_factory):
        proposal = fresh_factory.propose("humor")
        source = fresh_factory.generate_module(proposal)
        result = fresh_factory.validate_source(source)
        assert result["valid"] is True
        assert len(result["errors"]) == 0

    def test_syntax_error_fails(self, fresh_factory):
        result = fresh_factory.validate_source("def foo(\n")
        assert result["valid"] is False
        assert "Syntax error" in result["errors"][0]

    def test_dangerous_call_blocked(self, fresh_factory):
        bad = """
class Bad:
    pass

def _register():
    pass

eval("1+1")
"""
        result = fresh_factory.validate_source(bad)
        assert result["valid"] is False
        assert any("eval" in e for e in result["errors"])

    def test_missing_register_fails(self, fresh_factory):
        bad = """
class Bad:
    pass
"""
        result = fresh_factory.validate_source(bad)
        assert result["valid"] is False
        assert any("_register" in e for e in result["errors"])

    def test_missing_class_fails(self, fresh_factory):
        bad = """
def _register():
    pass
"""
        result = fresh_factory.validate_source(bad)
        assert result["valid"] is False
        assert any("class" in e for e in result["errors"])


class TestInstallation:
    def test_install_valid_module(self, fresh_factory):
        with tempfile.TemporaryDirectory() as tmpdir:
            proposal = fresh_factory.propose("routine")
            source = fresh_factory.generate_module(proposal)
            result = fresh_factory.install(proposal, source, project_root=tmpdir)
            assert result["success"] is True
            assert os.path.exists(result["path"])
            with open(result["path"]) as f:
                assert "class RoutineAwareness:" in f.read()

    def test_install_duplicate_blocked(self, fresh_factory):
        with tempfile.TemporaryDirectory() as tmpdir:
            proposal = fresh_factory.propose("routine")
            source = fresh_factory.generate_module(proposal)
            fresh_factory.install(proposal, source, project_root=tmpdir)
            result = fresh_factory.install(proposal, source, project_root=tmpdir)
            assert result["success"] is False
            assert result["reason"] == "file_exists"

    def test_install_invalid_blocked(self, fresh_factory):
        with tempfile.TemporaryDirectory() as tmpdir:
            proposal = fresh_factory.propose("routine")
            bad_source = "this is not valid python {"
            result = fresh_factory.install(proposal, bad_source, project_root=tmpdir)
            assert result["success"] is False
            assert result["reason"] == "validation_failed"
