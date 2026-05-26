"""ConsensusEngine — weighted voting and thread resolution for the Hive Mind."""

import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Optional

from infj_bot.hive_mind.protocol.dcp import DCPMessage, NodeRole, Resolution


class ThreadState(str, Enum):
    OPEN = "OPEN"
    RESOLVED = "RESOLVED"


@dataclass
class ConsensusThread:
    thread_id: str
    original_thought: DCPMessage
    state: ThreadState = ThreadState.OPEN
    resolution: Optional[DCPMessage] = None
    votes: Dict[str, str] = field(default_factory=dict)


class ConsensusEngine:
    """In-process consensus engine: propose → vote → resolve."""

    def __init__(self):
        self._threads: Dict[str, ConsensusThread] = {}

    def propose(self, msg: DCPMessage) -> ConsensusThread:
        thread_id = str(uuid.uuid4())[:8]
        thread = ConsensusThread(thread_id=thread_id, original_thought=msg)
        self._threads[thread_id] = thread
        return thread

    def vote(self, thread_id: str, voter_id: str, vote: str) -> None:
        if thread_id in self._threads:
            self._threads[thread_id].votes[voter_id] = vote

    def resolve(
        self,
        thread_id: str,
        resolution: Resolution,
        final_position: str = "",
    ) -> None:
        if thread_id not in self._threads:
            return
        thread = self._threads[thread_id]
        resolution_msg = DCPMessage(
            source_node="consensus",
            source_role=NodeRole.PRIMARY,
            content=final_position,
            name=resolution.value,
            payload={
                "resolution": resolution.value,
                "final_position": final_position,
                "voting_record": dict(thread.votes),
            },
        )
        thread.resolution = resolution_msg
        thread.state = ThreadState.RESOLVED

    def active_threads(self):
        return [t for t in self._threads.values() if t.state == ThreadState.OPEN]
