"""Tests for the structured Forge council artifacts."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from drift.trinity.council.council_runner import CouncilRunner
from drift.trinity.council.evidence_board import EvidenceBoard
from drift.trinity.council.evidence_packet import TrinityEvidencePacket
from drift.trinity.council.forge_council_schema import AgentMessage, ClaimStatus, MessageType


def test_agents_emit_typed_messages_only():
    runner = CouncilRunner(board=EvidenceBoard())
    context = {
        "subject": "authorized_audit_target",
        "claim": {"summary": "check the invariant path"},
    }

    for agent in runner.agents:
        message = agent.act(dict(context), runner.board)
        assert isinstance(message, AgentMessage)
        assert message.sender == agent.name
        assert message.message_type
        assert message.claim_id


def test_evidence_agent_is_only_accept_authority():
    board = EvidenceBoard()
    claim = board.create_claim(
        proposer="FormalEdgeAgent",
        subject="authorized_audit_target",
        content={"summary": "possible invariant issue"},
        confidence=0.4,
    )
    claim.evidence_refs.append("trace_01")
    claim.reproduction_status = "confirmed"

    with pytest.raises(PermissionError):
        board.add_message(
            AgentMessage(
                sender="ThreatModelAgent",
                receiver="Council",
                message_type=MessageType.ACCEPT.value,
                claim_id=claim.id,
                content={"reason": "trying to shortcut the gate"},
                evidence_refs=["trace_01"],
                confidence=0.95,
            )
        )

    board.add_message(
        AgentMessage(
            sender="EvidenceAgent",
            receiver="Council",
            message_type=MessageType.ACCEPT.value,
            claim_id=claim.id,
            content={"reason": "reproduced and defended"},
            evidence_refs=["trace_01"],
            confidence=0.95,
        )
    )

    assert board.get_claim(claim.id).status == ClaimStatus.ACCEPTED
    assert board.get_claim(claim.id).accepted_by == "EvidenceAgent"


def test_runner_creates_claim_and_board_summary():
    with tempfile.TemporaryDirectory() as tmp:
        board = EvidenceBoard(storage_path=Path(tmp) / "council_evidence.jsonl")
        runner = CouncilRunner(board=board)
        result = runner.run_round(
            {
                "subject": "authorized_audit_target",
                "claim": {"summary": "check the invariant path"},
                "evidence_refs": ["trace_01"],
            }
        )

        assert result["claim_id"]
        assert result["messages"]
        assert result["board"]["messages"] == len(runner.agents)
        assert result["board"]["claims"] >= 1



def test_runner_emits_evidence_packet_bundle():
    with tempfile.TemporaryDirectory() as tmp:
        bundle_root = Path(tmp) / "trinity_case_001"
        board = EvidenceBoard(storage_path=Path(tmp) / "council_evidence.jsonl")
        runner = CouncilRunner(board=board)
        result = runner.run_round(
            {
                "subject": "authorized_audit_target",
                "claim": {"summary": "check the invariant path"},
                "evidence_refs": ["trace_01"],
                "output_dir": bundle_root,
            }
        )

        packet = result["packet"]
        assert packet
        assert packet["status"] == "NEEDS_HUMAN_REVIEW"
        assert result["bundle_paths"]
        assert (bundle_root / "claim.json").exists()
        assert (bundle_root / "rejected_hypotheses.json").exists()
        assert (bundle_root / "reasoning_summary.md").exists()
        assert (bundle_root / "export_report.md").exists()
        assert (bundle_root / "evidence" / "tool_outputs").is_dir()
        assert "# Trinity Evidence Packet" in (bundle_root / "export_report.md").read_text(encoding="utf-8")


def test_reproduced_claim_packet_reports_real_status():
    board = EvidenceBoard()
    claim = board.create_claim(
        proposer="FormalEdgeAgent",
        subject="authorized_audit_target",
        content={"summary": "possible invariant issue"},
        confidence=0.4,
    )
    claim.evidence_refs.append("trace_01")
    claim.reproduction_status = "confirmed"
    board.accept_claim(claim.id, actor="EvidenceAgent", note="reproduced and defended")

    packet = TrinityEvidencePacket(
        claim=board.get_claim(claim.id).to_dict(),
        messages=[],
        board=board.summary(),
        reasoning_summary="Claim reproduced and accepted.",
    )

    assert packet.status() == "REPRODUCED_REAL"

