"""Hardened self-heal guard — two-key approval, deny lists, rollback, proof-gate enforcement."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable


DEFAULT_DENY_GLOBS = (
    ".env",
    ".env.*",
    "**/secrets/**",
    "**/keys/**",
    "**/.git/**",
    "**/firebase.json",
    "**/manifest.yaml",
    "anchor_server.py",
    "core/self_heal_guard.py",
)


@dataclass
class PatchProposal:
    path: str
    diff_summary: str
    proof_case_id: str | None = None
    test_passed: bool = False
    signal_promoted: bool = False
    approvals: set[str] = field(default_factory=set)


@dataclass
class SelfHealDecision:
    allowed: bool
    reason: str
    rollback_artifact: str | None = None


class SelfHealGuard:
    """Phase 4 optional module — never bypasses ANCHOR proof gate."""

    def __init__(
        self,
        *,
        deny_globs: Iterable[str] | None = None,
        required_approvals: Iterable[str] | None = None,
    ):
        self.deny_globs = tuple(deny_globs or DEFAULT_DENY_GLOBS)
        self.required_approvals = set(
            required_approvals
            or (
                "human_operator",
                "policy_engine",
            )
        )
        self.enabled = os.getenv("DRIFT_SELF_HEAL_ENABLED", "").strip() in {
            "1",
            "true",
            "yes",
        }

    def is_path_denied(self, path: str | Path) -> bool:
        target = Path(path).as_posix()
        for pattern in self.deny_globs:
            normalized = pattern.replace("**/", "")
            if normalized in target or target.endswith(normalized.lstrip("*")):
                return True
        return False

    def approve(self, proposal: PatchProposal, source: str) -> PatchProposal:
        proposal.approvals.add(source)
        return proposal

    def evaluate(self, proposal: PatchProposal) -> SelfHealDecision:
        if not self.enabled:
            return SelfHealDecision(
                allowed=False,
                reason="Self-heal module disabled (set DRIFT_SELF_HEAL_ENABLED=1)",
            )
        if self.is_path_denied(proposal.path):
            return SelfHealDecision(
                allowed=False,
                reason=f"Path denied by self-heal policy: {proposal.path}",
            )
        if not proposal.proof_case_id:
            return SelfHealDecision(
                allowed=False,
                reason="Proof case required — cannot patch without ledger case id",
            )
        if not proposal.signal_promoted:
            return SelfHealDecision(
                allowed=False,
                reason="Signal filter did not promote finding — queue for human review",
            )
        if not proposal.test_passed:
            return SelfHealDecision(
                allowed=False,
                reason="Tests must pass before auto-apply",
            )
        missing = self.required_approvals - proposal.approvals
        if missing:
            return SelfHealDecision(
                allowed=False,
                reason=f"Missing approvals: {', '.join(sorted(missing))}",
            )
        rollback = f"{proposal.path}.rollback.{proposal.proof_case_id}.patch"
        return SelfHealDecision(
            allowed=True,
            reason="Two-key approval satisfied; proof gate passed",
            rollback_artifact=rollback,
        )
