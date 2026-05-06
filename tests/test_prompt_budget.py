"""Tests for prompt budget tracking, deduplication, and debug dumps."""

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from prompt_budget import BudgetTier, PromptBudget


class TestBudgetTier:
    def test_add_within_budget(self):
        tier = BudgetTier("test", max_chars=100)
        assert tier.add("hello", label="greeting")
        assert tier.current_chars == 5
        assert tier.sections[0]["label"] == "greeting"

    def test_add_exceeds_budget(self):
        tier = BudgetTier("test", max_chars=10)
        assert not tier.add("this is way too long")
        assert tier.current_chars == 0

    def test_trim_to_fit(self):
        tier = BudgetTier("test", max_chars=40)
        trimmed = tier.trim_to_fit("this is a very long sentence indeed")
        assert len(trimmed) <= 40
        assert "[trimmed]" in trimmed

    def test_utilization(self):
        tier = BudgetTier("test", max_chars=100)
        tier.add("x" * 50)
        assert tier.utilization == 0.5


class TestPromptBudget:
    def test_add_and_assemble(self):
        budget = PromptBudget()
        budget.add("core", "Mode: companion")
        budget.add("cognitive", "Aspirations: grow")
        budget.set_footer("\nUser: hi\n")
        prompt = budget.assemble()
        assert "Mode: companion" in prompt
        assert "Aspirations: grow" in prompt
        assert "User: hi" in prompt

    def test_total_chars(self):
        budget = PromptBudget()
        budget.add("core", "abc")
        budget.add("cognitive", "def")
        budget.set_footer("ghi")
        assert budget.total_chars() == 9

    def test_trim_to_budget(self):
        budget = PromptBudget(max_total_chars=50)
        budget.add("core", "core text")
        budget.add("context", "x" * 100)
        budget.set_footer("footer")
        result = budget.trim_to_budget()
        assert len(result) <= 50 + 10  # allow small margin for footer
        assert "core text" in result

    def test_overlap_detection(self):
        budget = PromptBudget()
        budget.add("core", "The bot remains curious and kind.")
        budget.add("cognitive", "The bot remains curious and kind.")  # identical
        overlaps = budget.check_overlaps()
        assert len(overlaps) > 0
        assert any("bot remains curious" in o["phrase"] for o in overlaps)

    def test_no_false_overlap(self):
        budget = PromptBudget()
        budget.add("core", "Apples are red.")
        budget.add("cognitive", "Oranges are orange.")
        overlaps = budget.check_overlaps()
        # Should not flag unrelated phrases
        assert not any("apples are orange" in o["phrase"] for o in overlaps)

    def test_report(self):
        budget = PromptBudget()
        budget.add("core", "test")
        report = budget.report()
        assert "PROMPT BUDGET" in report
        assert "core" in report
        assert "TOTAL" in report

    def test_dump(self):
        budget = PromptBudget()
        budget.add("core", "hello world")
        with tempfile.TemporaryDirectory() as tmp:
            path = budget.dump(path=tmp + "/debug.json")
            data = json.loads(path.read_text())
            assert "budget" in data
            assert "assembled_prompt" in data
            assert data["assembled_prompt"] == "hello world"
            assert data["budget"]["total_chars"] == 11

    def test_unknown_tier_fallback(self):
        budget = PromptBudget()
        budget.add("nonexistent", "text")
        assert budget.tiers["cognitive"].current_chars == 4
