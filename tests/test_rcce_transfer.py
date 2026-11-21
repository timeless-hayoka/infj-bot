"""Characterization of explicit-principle transfer; no live-model claims."""

import pytest

from drift.core.rcce_transfer import PrincipleTransferPolicy


def test_explicit_principle_transfers_to_distinct_task(tmp_path):
    policy = PrincipleTransferPolicy(tmp_path / "transfer.db", failure_threshold=1)
    assert policy.record(
        task="parser",
        principle="diagnose-before-retry",
        strategy="retry unchanged",
        outcome="failure",
        verified=True,
        evidence="oracle failure",
    )
    restarted = PrincipleTransferPolicy(tmp_path / "transfer.db", failure_threshold=1)
    assert (
        restarted.choose(
            principle="diagnose-before-retry",
            candidates=["retry unchanged", "inspect cause"],
        ).strategy
        == "inspect cause"
    )


def test_unrelated_principle_does_not_inherit_history(tmp_path):
    policy = PrincipleTransferPolicy(tmp_path / "transfer.db", failure_threshold=1)
    policy.record(
        task="parser",
        principle="diagnose-before-retry",
        strategy="retry unchanged",
        outcome="failure",
        verified=True,
        evidence="oracle failure",
    )
    assert (
        policy.choose(
            principle="different-principle",
            candidates=["retry unchanged", "inspect cause"],
        ).strategy
        == "retry unchanged"
    )


def test_unverified_and_empty_evidence_fail_closed(tmp_path):
    policy = PrincipleTransferPolicy(tmp_path / "transfer.db", failure_threshold=1)
    assert not policy.record(
        task="parser",
        principle="diagnose-before-retry",
        strategy="retry unchanged",
        outcome="failure",
        verified=False,
        evidence="claim",
    )
    with pytest.raises(ValueError):
        policy.record(
            task="parser",
            principle="diagnose-before-retry",
            strategy="retry unchanged",
            outcome="failure",
            verified=True,
            evidence="",
        )
    assert (
        policy.choose(
            principle="diagnose-before-retry",
            candidates=["retry unchanged", "inspect cause"],
        ).strategy
        == "retry unchanged"
    )
