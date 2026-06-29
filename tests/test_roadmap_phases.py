"""Tests for phased roadmap modules (Phases 1–5)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.companion_plugin import companion_enabled, load_companion_config, require_companion
from core.memory_schema import MemoryLayer, MemoryModality, MemoryRecord, merge_records
from core.self_heal_guard import PatchProposal, SelfHealGuard
from drift.trinity.anchor_pipeline_bridge import PreprocessStats, _local_signal_filter
from drift.trinity.reasoning_cycle import ReasoningCycle


def test_memory_schema_merge_prefers_higher_salience():
    a = MemoryRecord(
        unified_id="a",
        layer=MemoryLayer.EPISODIC,
        modality=MemoryModality.TEXT,
        content="same",
        salience=0.4,
    )
    b = MemoryRecord(
        unified_id="b",
        layer=MemoryLayer.EPISODIC,
        modality=MemoryModality.TEXT,
        content="same",
        salience=0.8,
    )
    merged = merge_records(a, b)
    assert merged.salience == 0.8
    assert "merged_from" in merged.metadata


def test_local_signal_filter_drops_noise():
    findings = [
        {"title": "naming-convention", "labels": [], "summary": "x"},
        {"title": "reentrancy-eth", "labels": ["high"], "summary": "y"},
    ]
    kept, stats = _local_signal_filter(findings)
    assert len(kept) == 1
    assert stats.signal_discarded == 1
    assert stats.signal_promoted == 1


def test_reasoning_cycle_exports_claim():
    cycle = ReasoningCycle()
    goal = cycle.plan("Validate repro for case X", steps=["collect sarif", "run proof"])
    claim = cycle.export_claim(goal)
    assert claim.subject == "Validate repro for case X"
    assert claim.content["subtasks"] == ["collect sarif", "run proof"]
    assert 0.0 <= claim.confidence <= 1.0


def test_self_heal_guard_requires_two_keys(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DRIFT_SELF_HEAL_ENABLED", "1")
    guard = SelfHealGuard()
    proposal = PatchProposal(
        path="contracts/Vault.sol",
        diff_summary="fix",
        proof_case_id="case-1",
        test_passed=True,
        signal_promoted=True,
    )
    decision = guard.evaluate(proposal)
    assert not decision.allowed
    guard.approve(proposal, "human_operator")
    guard.approve(proposal, "policy_engine")
    decision = guard.evaluate(proposal)
    assert decision.allowed
    assert decision.rollback_artifact


def test_self_heal_guard_denies_protected_paths(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DRIFT_SELF_HEAL_ENABLED", "1")
    guard = SelfHealGuard()
    proposal = PatchProposal(
        path=".env",
        diff_summary="bad",
        proof_case_id="case-1",
        test_passed=True,
        signal_promoted=True,
    )
    guard.approve(proposal, "human_operator")
    guard.approve(proposal, "policy_engine")
    assert not guard.evaluate(proposal).allowed


def test_companion_plugin_disabled_by_default(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("DRIFT_COMPANION_ENABLED", raising=False)
    assert not companion_enabled()
    with pytest.raises(RuntimeError):
        require_companion("hive")


def test_companion_plugin_enabled(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DRIFT_COMPANION_ENABLED", "1")
    cfg = load_companion_config()
    assert cfg.enabled
    assert cfg.hive


def test_preprocess_stats_serializable():
    stats = PreprocessStats(ingested=3, signal_promoted=2)
    payload = stats.to_dict()
    assert json.loads(json.dumps(payload)) == payload


def test_anchor_root_resolves_sibling_repo():
    from drift.trinity.anchor_pipeline_bridge import resolve_anchor_root

    root = resolve_anchor_root()
    if root is not None:
        assert (root / "anchor_sarif" / "pipeline.py").is_file()
