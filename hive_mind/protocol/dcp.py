"""Distributed Cognition Protocol — message types, roles, and resolutions."""

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class NodeRole(str, Enum):
    PRIMARY = "PRIMARY"
    CRITIC = "CRITIC"
    BACKUP = "BACKUP"
    OBSERVER = "OBSERVER"


class Resolution(str, Enum):
    ADOPTED = "ADOPTED"
    TABLED = "TABLED"
    REJECTED = "REJECTED"
    PENDING = "PENDING"


@dataclass
class DCPMessage:
    """A message in the Distributed Cognition Protocol."""

    source_node: str
    source_role: NodeRole
    content: str
    name: str = "thought"
    priority: float = 0.5
    payload: dict = field(default_factory=dict)
    message_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    @classmethod
    def thought(
        cls,
        source_node: str,
        source_role: NodeRole,
        content: str,
        priority: float = 0.5,
    ) -> "DCPMessage":
        return cls(
            source_node=source_node,
            source_role=source_role,
            content=content,
            name="thought",
            priority=priority,
        )
