"""Structured council schema for DRIFT / Trinity reasoning.

The council communicates through typed artifacts instead of freeform chat.
This keeps proposals, challenges, evidence, and state transitions machine-checkable.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import uuid4


def utc_stamp() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


class ClaimStatus(str, Enum):
    PROPOSED = "proposed"
    CHALLENGED = "challenged"
    EVIDENCE_REQUESTED = "evidence_requested"
    REPRO_ATTEMPTED = "repro_attempted"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    MEMORY_UPDATED = "memory_updated"


class MessageType(str, Enum):
    PROPOSAL = "proposal"
    CLAIM_REFINEMENT = "claim_refinement"
    CHALLENGE = "challenge"
    EVIDENCE_REQUEST = "evidence_request"
    REPRO_ATTEMPT = "repro_attempt"
    ACCEPT = "accept"
    REJECT = "reject"
    MEMORY_UPDATE = "memory_update"
    STRATEGY_UPDATE = "strategy_update"


@dataclass
class AgentState:
    role: str
    score: float = 0.5
    authority: float = 0.5
    recent_performance: List[float] = field(default_factory=list)
    drive_state: Dict[str, float] = field(default_factory=dict)
    memory_refs: List[str] = field(default_factory=list)

    def observe(self, performance: float) -> None:
        self.recent_performance.append(performance)
        self.recent_performance = self.recent_performance[-12:]
        if self.recent_performance:
            self.score = round(
                sum(self.recent_performance) / len(self.recent_performance), 4
            )


@dataclass
class AgentMessage:
    sender: str
    receiver: str
    message_type: str
    claim_id: Optional[str]
    content: Dict[str, Any]
    evidence_refs: List[str]
    confidence: float
    requires_response: bool = False
    timestamp: str = field(default_factory=utc_stamp)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class EvidenceItem:
    id: str
    source_agent: str
    evidence_type: str
    content: Dict[str, Any]
    strength: float
    reproducible: bool = False
    claim_id: Optional[str] = None
    timestamp: str = field(default_factory=utc_stamp)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ClaimRecord:
    id: str
    status: ClaimStatus = ClaimStatus.PROPOSED
    proposer: str = ""
    subject: str = ""
    content: Dict[str, Any] = field(default_factory=dict)
    evidence_refs: List[str] = field(default_factory=list)
    challenge_notes: List[str] = field(default_factory=list)
    disproof_attempts: List[str] = field(default_factory=list)
    reproduction_status: str = "unattempted"
    confidence: float = 0.0
    accepted_by: Optional[str] = None
    memory_updated: bool = False
    created_at: str = field(default_factory=utc_stamp)
    updated_at: str = field(default_factory=utc_stamp)

    def touch(self) -> None:
        self.updated_at = utc_stamp()

    def add_evidence(self, evidence_ref: str) -> None:
        if evidence_ref not in self.evidence_refs:
            self.evidence_refs.append(evidence_ref)
            self.touch()

    def transition(
        self,
        new_status: ClaimStatus,
        actor: str,
        note: str | None = None,
    ) -> None:
        if new_status == ClaimStatus.ACCEPTED and actor != "EvidenceAgent":
            raise PermissionError("Only EvidenceAgent can promote a claim to ACCEPTED.")

        if note:
            if new_status == ClaimStatus.CHALLENGED:
                self.challenge_notes.append(note)
            elif new_status == ClaimStatus.REPRO_ATTEMPTED:
                self.disproof_attempts.append(note)
            elif new_status == ClaimStatus.REJECTED:
                self.disproof_attempts.append(note)

        self.status = new_status
        self.touch()

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["status"] = self.status.value
        return payload


def new_claim_id(prefix: str = "claim") -> str:
    return f"{prefix}_{uuid4().hex[:10]}"
