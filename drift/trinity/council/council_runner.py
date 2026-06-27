"""Minimal structured council runner for DRIFT / Trinity.

Each agent emits exactly one AgentMessage per round. The evidence board stores
those messages and enforces claim lifecycle authority.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .evidence_board import EvidenceBoard
from .evidence_packet import TrinityEvidencePacket, build_reasoning_summary
from .forge_council_schema import (
    AgentMessage,
    AgentState,
    MessageType,
    new_claim_id,
)


class BaseCouncilAgent:
    name = "BaseCouncilAgent"
    receiver = "Council"

    def __init__(self) -> None:
        self.state = AgentState(role=self.name)
        self.memory: List[AgentMessage] = []

    def remember(self, message: AgentMessage) -> None:
        self.memory.append(message)
        self.state.memory_refs.append(message.claim_id or message.sender)
        self.state.memory_refs = self.state.memory_refs[-24:]

    def build_message(
        self,
        *,
        receiver: str,
        message_type: MessageType,
        claim_id: str | None,
        content: Dict[str, Any],
        evidence_refs: Optional[List[str]] = None,
        confidence: float = 0.5,
        requires_response: bool = False,
    ) -> AgentMessage:
        return AgentMessage(
            sender=self.name,
            receiver=receiver,
            message_type=message_type.value,
            claim_id=claim_id,
            content=content,
            evidence_refs=list(evidence_refs or []),
            confidence=confidence,
            requires_response=requires_response,
        )

    def act(self, context: Dict[str, Any], board: EvidenceBoard) -> AgentMessage:
        raise NotImplementedError


class FormalEdgeAgent(BaseCouncilAgent):
    name = "FormalEdgeAgent"

    def act(self, context: Dict[str, Any], board: EvidenceBoard) -> AgentMessage:
        claim = _ensure_claim(context, board, proposer=self.name)
        content = {
            "subject": claim.subject,
            "invariants": context.get("invariants", []),
            "impossible_states": context.get("impossible_states", []),
            "summary": "formal refinement",
        }
        return self.build_message(
            receiver="EvidenceAgent",
            message_type=MessageType.CLAIM_REFINEMENT,
            claim_id=claim.id,
            content=content,
            evidence_refs=list(claim.evidence_refs),
            confidence=min(1.0, max(0.2, claim.confidence + 0.1)),
        )


class FuzzMutationAgent(BaseCouncilAgent):
    name = "FuzzMutationAgent"

    def act(self, context: Dict[str, Any], board: EvidenceBoard) -> AgentMessage:
        claim = _ensure_claim(context, board, proposer=self.name)
        content = {
            "subject": claim.subject,
            "mutation_seed": context.get("seed", "structured_default"),
            "mutation_targets": context.get("mutation_targets", []),
            "summary": "coverage-guided mutation request",
        }
        return self.build_message(
            receiver="ContrarianAgent",
            message_type=MessageType.EVIDENCE_REQUEST,
            claim_id=claim.id,
            content=content,
            evidence_refs=list(claim.evidence_refs),
            confidence=0.45,
            requires_response=True,
        )


class ThreatModelAgent(BaseCouncilAgent):
    name = "ThreatModelAgent"

    def act(self, context: Dict[str, Any], board: EvidenceBoard) -> AgentMessage:
        claim = _ensure_claim(context, board, proposer=self.name)
        content = {
            "subject": claim.subject,
            "attacker_capability": context.get("attacker_capability", "authorized_observer"),
            "assumption": context.get("assumption", "external influence exists"),
            "failure_modes": context.get("failure_modes", []),
            "summary": "threat model escalation",
        }
        return self.build_message(
            receiver="EvidenceAgent",
            message_type=MessageType.CHALLENGE,
            claim_id=claim.id,
            content=content,
            evidence_refs=list(claim.evidence_refs),
            confidence=0.52,
            requires_response=True,
        )


class ContrarianAgent(BaseCouncilAgent):
    name = "ContrarianAgent"

    ATTACK_MODES = (
        "missing_precondition",
        "false_assumption",
        "toy_environment",
        "owner_only_path",
        "impossible_attacker_capability",
        "non_profitable_exploit",
        "already_mitigated",
        "test_artifact_only",
        "decimal_or_rounding_mistake",
    )

    def act(self, context: Dict[str, Any], board: EvidenceBoard) -> AgentMessage:
        claim = _ensure_claim(context, board, proposer=self.name)
        attack_mode = context.get("attack_mode") or self.ATTACK_MODES[
            len(claim.challenge_notes) % len(self.ATTACK_MODES)
        ]
        content = {
            "subject": claim.subject,
            "attack_mode": attack_mode,
            "counter_examples": context.get("counter_examples", []),
            "summary": "claim challenge",
        }
        return self.build_message(
            receiver="EvidenceAgent",
            message_type=MessageType.CHALLENGE,
            claim_id=claim.id,
            content=content,
            evidence_refs=list(claim.evidence_refs),
            confidence=0.38,
            requires_response=True,
        )


class EvidenceAgent(BaseCouncilAgent):
    name = "EvidenceAgent"

    def act(self, context: Dict[str, Any], board: EvidenceBoard) -> AgentMessage:
        claim = _ensure_claim(context, board, proposer=self.name)
        has_evidence = bool(claim.evidence_refs or context.get("evidence_refs"))
        repro_ready = claim.reproduction_status in {"reproduced", "confirmed"}
        if has_evidence and repro_ready:
            content = {
                "reason": "claim verified with evidence and reproduction",
                "reproduction_status": claim.reproduction_status,
            }
            message_type = MessageType.ACCEPT
            confidence = min(1.0, max(0.7, claim.confidence + 0.2))
        elif has_evidence:
            content = {
                "reason": "evidence present but reproduction pending",
                "requested_artifacts": ["trace", "diff", "command_result"],
            }
            message_type = MessageType.EVIDENCE_REQUEST
            confidence = 0.55
        else:
            content = {
                "reason": "no evidence refs attached",
                "requested_artifacts": ["trace", "logs", "test_output"],
            }
            message_type = MessageType.EVIDENCE_REQUEST
            confidence = 0.3

        return self.build_message(
            receiver="Council",
            message_type=message_type,
            claim_id=claim.id,
            content=content,
            evidence_refs=list(claim.evidence_refs),
            confidence=confidence,
            requires_response=(message_type != MessageType.ACCEPT),
        )


class StrategyEvolutionAgent(BaseCouncilAgent):
    name = "StrategyEvolutionAgent"

    def act(self, context: Dict[str, Any], board: EvidenceBoard) -> AgentMessage:
        claim = _ensure_claim(context, board, proposer=self.name)
        content = {
            "subject": claim.subject,
            "updated_weights": context.get(
                "updated_weights",
                {"formal": 0.25, "fuzz": 0.25, "threat": 0.2, "evidence": 0.3},
            ),
            "selection_rule": "mutate after verification",
            "summary": "strategy update",
        }
        return self.build_message(
            receiver="Council",
            message_type=MessageType.STRATEGY_UPDATE,
            claim_id=claim.id,
            content=content,
            evidence_refs=list(claim.evidence_refs),
            confidence=0.44,
        )


def _ensure_claim(context: Dict[str, Any], board: EvidenceBoard, proposer: str):
    claim_id = context.get("claim_id")
    subject = context.get("subject", "authorized_audit_target")
    claim_content = context.get("claim", {})

    if claim_id and board.get_claim(claim_id):
        return board.get_claim(claim_id)

    if not claim_id:
        claim_id = context.setdefault("claim_id", new_claim_id())

    existing = board.get_claim(claim_id)
    if existing:
        return existing

    return board.create_claim(
        proposer=proposer,
        subject=subject,
        content=claim_content if isinstance(claim_content, dict) else {"raw": claim_content},
        confidence=float(context.get("confidence", 0.0)),
        claim_id=claim_id,
    )


class CouncilRunner:
    def __init__(self, board: EvidenceBoard | None = None):
        self.board = board or EvidenceBoard()
        self.agents = [
            FormalEdgeAgent(),
            FuzzMutationAgent(),
            ThreatModelAgent(),
            ContrarianAgent(),
            EvidenceAgent(),
            StrategyEvolutionAgent(),
        ]

    def run_round(self, context: Dict[str, Any]) -> Dict[str, Any]:
        round_context = dict(context)
        messages: List[AgentMessage] = []

        for agent in self.agents:
            message = agent.act(round_context, self.board)
            messages.append(message)
            agent.remember(message)
            self.board.add_message(message)

        claim_id = round_context.get("claim_id")
        claim = self.board.get_claim(claim_id) if claim_id else None
        board_summary = self.board.summary()
        packet = None
        bundle_paths = None

        if claim is not None:
            message_dicts = [message.to_dict() for message in messages]
            rejected_hypotheses = []
            for message in message_dicts:
                if message.get("message_type") in {
                    MessageType.CHALLENGE.value,
                    MessageType.EVIDENCE_REQUEST.value,
                    MessageType.REJECT.value,
                }:
                    content = message.get("content", {}) or {}
                    reason = (
                        content.get("reason")
                        or content.get("attack_mode")
                        or content.get("request")
                        or content.get("summary")
                        or "needs review"
                    )
                    rejected_hypotheses.append(
                        {
                            "sender": message.get("sender"),
                            "message_type": message.get("message_type"),
                            "reason": reason,
                            "claim_id": message.get("claim_id"),
                            "evidence_refs": message.get("evidence_refs", []),
                        }
                    )
            packet = TrinityEvidencePacket(
                claim=claim.to_dict(),
                messages=message_dicts,
                board=board_summary,
                rejected_hypotheses=rejected_hypotheses,
                reasoning_summary=build_reasoning_summary(claim, message_dicts, board_summary),
                reproduction_command=round_context.get("reproduction_command"),
            )
            output_dir = round_context.get("output_dir") or round_context.get("packet_root")
            if output_dir:
                bundle_paths = packet.write_bundle(output_dir)

        return {
            "claim_id": claim_id,
            "messages": [message.to_dict() for message in messages],
            "claim": claim.to_dict() if claim else None,
            "board": board_summary,
            "packet": packet.to_dict() if packet else None,
            "bundle_paths": bundle_paths,
        }
