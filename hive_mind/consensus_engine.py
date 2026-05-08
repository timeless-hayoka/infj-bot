"""Consensus Engine — multi-node reasoning: propose → critique → integrate → resolve."""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from protocol.dcp import DCPMessage, MessageType, Resolution, NodeRole


class ThreadState(Enum):
    OPEN = "OPEN"
    CRITIQUING = "CRITIQUING"
    INTEGRATING = "INTEGRATING"
    RESOLVED = "RESOLVED"
    EXPIRED = "EXPIRED"


@dataclass
class ConsensusThread:
    thread_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    state: ThreadState = ThreadState.OPEN
    created_at: float = field(default_factory=time.time)
    resolved_at: Optional[float] = None
    original_thought: Optional[DCPMessage] = None
    critiques: list[DCPMessage] = field(default_factory=list)
    integrations: list[DCPMessage] = field(default_factory=list)
    resolution: Optional[DCPMessage] = None
    participation: dict[str, str] = field(default_factory=dict)  # node_id -> role


class ConsensusEngine:
    """Orchestrates structured reasoning across multiple nodes."""

    def __init__(
        self,
        adoption_threshold: float = 0.66,
        critique_timeout: float = 30.0,
        integration_timeout: float = 60.0,
    ) -> None:
        self.adoption_threshold = adoption_threshold
        self.critique_timeout = critique_timeout
        self.integration_timeout = integration_timeout
        self._threads: dict[str, ConsensusThread] = {}
        self._node_votes: dict[str, dict[str, str]] = {}  # thread_id -> {node_id: vote}

    # --- Thread Lifecycle ---

    def propose(self, thought: DCPMessage) -> ConsensusThread:
        """Start a new consensus thread from a THOUGHT message."""
        thread = ConsensusThread(
            thread_id=thought.thread_id,
            state=ThreadState.OPEN,
            original_thought=thought,
            participation={thought.source_node: thought.source_role},
        )
        self._threads[thread.thread_id] = thread
        self._node_votes[thread.thread_id] = {}
        return thread

    def critique(self, thread_id: str, critique: DCPMessage) -> ConsensusThread:
        """Add a critique to an open thread."""
        thread = self._threads.get(thread_id)
        if not thread or thread.state not in (ThreadState.OPEN, ThreadState.CRITIQUING):
            raise ValueError(f"Thread {thread_id} not open for critique")

        thread.critiques.append(critique)
        thread.participation[critique.source_node] = critique.source_role
        thread.state = ThreadState.CRITIQUING
        return thread

    def integrate(self, thread_id: str, integration: DCPMessage) -> ConsensusThread:
        """Add an integration synthesis."""
        thread = self._threads.get(thread_id)
        if not thread or thread.state not in (ThreadState.CRITIQUING, ThreadState.INTEGRATING):
            raise ValueError(f"Thread {thread_id} not ready for integration")

        thread.integrations.append(integration)
        thread.participation[integration.source_node] = integration.source_role
        thread.state = ThreadState.INTEGRATING
        return thread

    def resolve(
        self,
        thread_id: str,
        resolution_type: Resolution,
        resolver_node: str = "orchestrator",
        final_position: str = "",
    ) -> ConsensusThread:
        """Resolve a thread based on current votes and confidence."""
        thread = self._threads.get(thread_id)
        if not thread:
            raise ValueError(f"Thread {thread_id} not found")

        votes = self._node_votes.get(thread_id, {})
        confidence = self._calculate_confidence(thread, votes)

        # Watcher veto blocks adoption
        if resolution_type == Resolution.ADOPTED:
            for node, vote in votes.items():
                if vote == "BLOCK" and thread.participation.get(node) == NodeRole.WATCHER.value:
                    resolution_type = Resolution.TABLED
                    final_position = f"Blocked by Watcher ({node}). Reason: {final_position}"
                    break

            if confidence < self.adoption_threshold:
                resolution_type = Resolution.NEEDS_MORE_DATA

        resolution = DCPMessage(
            source_node=resolver_node,
            source_role=NodeRole.WATCHER.value,
            message_type=MessageType.RESOLVE.value,
            thread_id=thread_id,
            priority=0.8,
            payload={
                "thread_id": thread_id,
                "resolution": resolution_type.value,
                "final_position": final_position,
                "voting_record": votes,
                "confidence": confidence,
                "next_action": None,
            },
        )

        thread.resolution = resolution
        thread.state = ThreadState.RESOLVED
        thread.resolved_at = time.time()
        return thread

    def vote(self, thread_id: str, node_id: str, vote: str) -> None:
        """Cast a vote: FOR, AGAINST, ABSTAIN, or BLOCK (Watcher only)."""
        if thread_id not in self._node_votes:
            self._node_votes[thread_id] = {}
        self._node_votes[thread_id][node_id] = vote

    # --- Queries ---

    def get_thread(self, thread_id: str) -> Optional[ConsensusThread]:
        return self._threads.get(thread_id)

    def active_threads(self) -> list[ConsensusThread]:
        return [t for t in self._threads.values() if t.state != ThreadState.RESOLVED]

    def expired_threads(self, now: Optional[float] = None) -> list[ConsensusThread]:
        now = now or time.time()
        expired = []
        for t in self._threads.values():
            if t.state == ThreadState.RESOLVED:
                continue
            age = now - t.created_at
            if t.state == ThreadState.CRITIQUING and age > self.critique_timeout:
                expired.append(t)
            elif t.state == ThreadState.INTEGRATING and age > self.integration_timeout:
                expired.append(t)
        return expired

    def auto_resolve_expired(self) -> list[ConsensusThread]:
        resolved = []
        for thread in self.expired_threads():
            thread.state = ThreadState.EXPIRED
            thread.resolved_at = time.time()
            thread.resolution = DCPMessage(
                source_node="orchestrator",
                source_role=NodeRole.WATCHER.value,
                message_type=MessageType.RESOLVE.value,
                thread_id=thread.thread_id,
                priority=0.5,
                payload={
                    "thread_id": thread.thread_id,
                    "resolution": Resolution.TABLED.value,
                    "final_position": "Thread expired due to timeout.",
                    "voting_record": self._node_votes.get(thread.thread_id, {}),
                    "confidence": 0.0,
                    "next_action": None,
                },
            )
            resolved.append(thread)
        return resolved

    # --- Scoring ---

    def _calculate_confidence(self, thread: ConsensusThread, votes: dict[str, str]) -> float:
        if not votes:
            return thread.original_thought.payload.get("confidence", 0.5) if thread.original_thought else 0.5

        for_votes = sum(1 for v in votes.values() if v == "FOR")
        against_votes = sum(1 for v in votes.values() if v == "AGAINST")
        total = for_votes + against_votes
        if total == 0:
            return 0.5

        raw_ratio = for_votes / total
        # Boost confidence if high-consensus critiques were addressed
        critique_severities = [
            c.payload.get("severity", 0.5)
            for c in thread.critiques
        ]
        avg_severity = sum(critique_severities) / len(critique_severities) if critique_severities else 0.0
        # Higher unaddressed severity → lower confidence
        penalty = avg_severity * 0.2 if not thread.integrations else avg_severity * 0.05
        return max(0.0, min(1.0, raw_ratio - penalty))

    def summary(self, thread_id: str) -> dict[str, Any]:
        thread = self._threads.get(thread_id)
        if not thread:
            return {"error": "Thread not found"}
        return {
            "thread_id": thread_id,
            "state": thread.state.value,
            "age_seconds": round(time.time() - thread.created_at, 1),
            "participants": list(thread.participation.keys()),
            "thoughts": 1 if thread.original_thought else 0,
            "critiques": len(thread.critiques),
            "integrations": len(thread.integrations),
            "votes": self._node_votes.get(thread_id, {}),
            "resolved": thread.state == ThreadState.RESOLVED,
        }

    def hive_stats(self) -> dict[str, Any]:
        total = len(self._threads)
        by_state = {}
        for t in self._threads.values():
            by_state[t.state.value] = by_state.get(t.state.value, 0) + 1
        avg_resolution_time = 0.0
        resolved = [t for t in self._threads.values() if t.resolved_at]
        if resolved:
            avg_resolution_time = sum(
                t.resolved_at - t.created_at for t in resolved if t.resolved_at
            ) / len(resolved)
        return {
            "total_threads": total,
            "by_state": by_state,
            "avg_resolution_time": round(avg_resolution_time, 1),
            "adoption_threshold": self.adoption_threshold,
        }
