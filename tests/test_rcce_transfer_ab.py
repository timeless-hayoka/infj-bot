"""RCCE-1 deterministic strategy-transfer A/B; offline, NOT a live-model score."""
from drift.core.rcce_transfer import PrincipleTransferPolicy


def test_transfer_ab_uses_isolated_stores_and_identical_candidates(tmp_path):
    enabled = PrincipleTransferPolicy(tmp_path / "enabled.sqlite", failure_threshold=1)
    disabled = PrincipleTransferPolicy(tmp_path / "disabled.sqlite", failure_threshold=1)
    candidates = ["retry unchanged", "inspect cause"]
    principle = "diagnose-before-retry"
    # Both groups must start with identical decisions.
    assert enabled.choose(principle=principle, candidates=candidates).strategy == (
        disabled.choose(principle=principle, candidates=candidates).strategy
    )
    assert enabled.record(
        task="parser timeout", principle=principle,
        strategy="retry unchanged", outcome="failure",
        verified=True, evidence="deterministic failure oracle",
    )
    # Distinct unseen task uses the externally assigned principle.
    enabled = PrincipleTransferPolicy(tmp_path / "enabled.sqlite", failure_threshold=1)
    disabled = PrincipleTransferPolicy(tmp_path / "disabled.sqlite", failure_threshold=1)
    assert enabled.choose(principle=principle, candidates=candidates).strategy == "inspect cause"
    assert disabled.choose(principle=principle, candidates=candidates).strategy == "retry unchanged"
    assert enabled.choose(principle="unrelated", candidates=candidates).strategy == (
        disabled.choose(principle="unrelated", candidates=candidates).strategy
    )
