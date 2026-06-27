"""Shared evidence board for council claims.

The board stores claims, evidence items, and enforces the promotion rule:
only EvidenceAgent may accept a claim.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from .forge_council_schema import (
    AgentMessage,
    ClaimRecord,
    ClaimStatus,
    EvidenceItem,
    MessageType,
    new_claim_id,
)


class EvidenceBoard:
    def __init__(self, storage_path: str | Path | None = None):
        self.storage_path = Path(storage_path) if storage_path else None
        self.claims: Dict[str, ClaimRecord] = {}
        self.evidence_items: Dict[str, EvidenceItem] = {}
        self.messages: List[AgentMessage] = []

        if self.storage_path:
            self.storage_path.parent.mkdir(parents=True, exist_ok=True)
            if self.storage_path.exists():
                self._load()

    def _load(self) -> None:
        assert self.storage_path is not None
        try:
            with self.storage_path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    record = json.loads(line)
                    kind = record.get("kind")
                    if kind == "claim":
                        claim = ClaimRecord(**record["payload"])
                        claim.status = ClaimStatus(claim.status)
                        self.claims[claim.id] = claim
                    elif kind == "evidence":
                        item = EvidenceItem(**record["payload"])
                        self.evidence_items[item.id] = item
        except FileNotFoundError:
            return

    def _append_record(self, kind: str, payload: Dict[str, Any]) -> None:
        if not self.storage_path:
            return
        with self.storage_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"kind": kind, "payload": payload}) + "\n")

    def create_claim(
        self,
        proposer: str,
        subject: str,
        content: Dict[str, Any],
        confidence: float = 0.0,
        claim_id: str | None = None,
    ) -> ClaimRecord:
        claim = ClaimRecord(
            id=claim_id or new_claim_id(),
            proposer=proposer,
            subject=subject,
            content=content,
            confidence=confidence,
        )
        self.claims[claim.id] = claim
        self._append_record("claim", claim.to_dict())
        return claim

    def get_claim(self, claim_id: str) -> Optional[ClaimRecord]:
        return self.claims.get(claim_id)

    def add_message(self, message: AgentMessage) -> None:
        self.messages.append(message)
        if message.claim_id:
            self._apply_message(message)

    def add_evidence(self, item: EvidenceItem) -> EvidenceItem:
        self.evidence_items[item.id] = item
        if item.claim_id and item.claim_id in self.claims:
            claim = self.claims[item.claim_id]
            claim.add_evidence(item.id)
            claim.transition(
                ClaimStatus.EVIDENCE_REQUESTED,
                actor=item.source_agent,
                note=f"evidence:{item.id}",
            )
        self._append_record("evidence", item.to_dict())
        return item

    def accept_claim(self, claim_id: str, actor: str, note: str | None = None) -> ClaimRecord:
        claim = self._require_claim(claim_id)
        claim.transition(ClaimStatus.ACCEPTED, actor=actor, note=note)
        claim.accepted_by = actor
        self._append_record("claim", claim.to_dict())
        return claim

    def reject_claim(self, claim_id: str, actor: str, note: str | None = None) -> ClaimRecord:
        claim = self._require_claim(claim_id)
        claim.transition(ClaimStatus.REJECTED, actor=actor, note=note)
        self._append_record("claim", claim.to_dict())
        return claim

    def mark_memory_updated(self, claim_id: str, actor: str, note: str | None = None) -> ClaimRecord:
        claim = self._require_claim(claim_id)
        claim.transition(ClaimStatus.MEMORY_UPDATED, actor=actor, note=note)
        claim.memory_updated = True
        self._append_record("claim", claim.to_dict())
        return claim

    def summary(self) -> Dict[str, Any]:
        counts = {status.value: 0 for status in ClaimStatus}
        for claim in self.claims.values():
            counts[claim.status.value] += 1
        return {
            "claims": len(self.claims),
            "evidence_items": len(self.evidence_items),
            "messages": len(self.messages),
            "status_counts": counts,
        }

    def _apply_message(self, message: AgentMessage) -> None:
        claim = self.claims.get(message.claim_id)
        if claim is None and message.message_type == MessageType.PROPOSAL.value:
            claim = self.create_claim(
                proposer=message.sender,
                subject=message.content.get("subject", "unknown"),
                content=message.content,
                confidence=message.confidence,
                claim_id=message.claim_id,
            )
        elif claim is None:
            return

        if message.message_type == MessageType.PROPOSAL.value:
            claim.transition(
                ClaimStatus.PROPOSED,
                actor=message.sender,
                note=message.content.get("summary", "proposal"),
            )
        elif message.message_type == MessageType.CLAIM_REFINEMENT.value:
            claim.content.update(message.content)
            claim.confidence = max(claim.confidence, message.confidence)
            claim.transition(
                ClaimStatus.PROPOSED,
                actor=message.sender,
                note=message.content.get("summary", "refinement"),
            )
        elif message.message_type == MessageType.CHALLENGE.value:
            claim.transition(
                ClaimStatus.CHALLENGED,
                actor=message.sender,
                note=message.content.get("attack_mode", "challenge"),
            )
        elif message.message_type == MessageType.EVIDENCE_REQUEST.value:
            claim.transition(
                ClaimStatus.EVIDENCE_REQUESTED,
                actor=message.sender,
                note=message.content.get("request", "evidence request"),
            )
        elif message.message_type == MessageType.REPRO_ATTEMPT.value:
            claim.reproduction_status = message.content.get("status", "attempted")
            claim.transition(
                ClaimStatus.REPRO_ATTEMPTED,
                actor=message.sender,
                note=message.content.get("details", "repro attempt"),
            )
        elif message.message_type == MessageType.ACCEPT.value:
            self.accept_claim(
                claim.id,
                actor=message.sender,
                note=message.content.get("reason"),
            )
        elif message.message_type == MessageType.REJECT.value:
            self.reject_claim(
                claim.id,
                actor=message.sender,
                note=message.content.get("reason"),
            )
        elif message.message_type == MessageType.MEMORY_UPDATE.value:
            self.mark_memory_updated(
                claim.id,
                actor=message.sender,
                note=message.content.get("reason"),
            )

    def _require_claim(self, claim_id: str) -> ClaimRecord:
        claim = self.claims.get(claim_id)
        if claim is None:
            raise KeyError(f"Unknown claim_id: {claim_id}")
        return claim
