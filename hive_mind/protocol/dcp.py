"""DRIFT Communication Protocol (DCP) v1.0 — message encoding, validation, transport."""
from __future__ import annotations

import json
import hashlib
import time
import uuid
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Any, Optional


class MessageType(Enum):
    THOUGHT = "THOUGHT"
    CRITIQUE = "CRITIQUE"
    INTEGRATE = "INTEGRATE"
    RESOLVE = "RESOLVE"
    SYNC = "SYNC"
    HEARTBEAT = "HEARTBEAT"
    ALERT = "ALERT"


class NodeRole(Enum):
    PRIMARY = "primary"
    CRITIC = "critic"
    ARCHITECT = "architect"
    EMPATH = "empath"
    WATCHER = "watcher"
    SATELLITE = "satellite"


class Resolution(Enum):
    ADOPTED = "ADOPTED"
    REJECTED = "REJECTED"
    TABLED = "TABLED"
    NEEDS_MORE_DATA = "NEEDS_MORE_DATA"


class AlertType(Enum):
    SAFETY = "SAFETY"
    COHERENCE_DROP = "COHERENCE_DROP"
    NODE_FAILURE = "NODE_FAILURE"
    SECURITY = "SECURITY"
    HUMAN_NEEDS_HELP = "HUMAN_NEEDS_HELP"


class NodeStatus(Enum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    OVERLOADED = "OVERLOADED"
    RECOVERING = "RECOVERING"
    QUARANTINED = "QUARANTINED"
    OFFLINE = "OFFLINE"


@dataclass
class DCPMessage:
    dcp_version: str = "1.0"
    message_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%S.", time.gmtime()) + f"{time.time_ns() % 1_000_000:06d}Z")
    source_node: str = ""
    source_role: str = NodeRole.SATELLITE.value
    message_type: str = MessageType.THOUGHT.value
    thread_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    in_reply_to: Optional[str] = None
    priority: float = 0.5
    ttl: int = 300
    payload: dict[str, Any] = field(default_factory=dict)
    signature: Optional[str] = None

    def to_json(self) -> str:
        return json.dumps(asdict(self), default=str, indent=None, separators=(",", ":"))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def hash(self) -> str:
        """Stable hash for deduplication and signing."""
        canonical = json.dumps(asdict(self), default=str, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()[:32]

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "DCPMessage":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})

    @classmethod
    def from_json(cls, s: str) -> "DCPMessage":
        return cls.from_dict(json.loads(s))

    # --- Factory methods for common message types ---

    @classmethod
    def thought(
        cls,
        source_node: str,
        source_role: NodeRole,
        content: str,
        domain: str = "general",
        confidence: float = 0.5,
        evidence: Optional[list[str]] = None,
        requested_roles: Optional[list[str]] = None,
        thread_id: Optional[str] = None,
        priority: float = 0.5,
    ) -> "DCPMessage":
        return cls(
            source_node=source_node,
            source_role=source_role.value,
            message_type=MessageType.THOUGHT.value,
            thread_id=thread_id or str(uuid.uuid4()),
            priority=priority,
            payload={
                "domain": domain,
                "content": content,
                "confidence": confidence,
                "evidence": evidence or [],
                "requested_roles": requested_roles or [],
                "proposed_action": None,
            },
        )

    @classmethod
    def critique(
        cls,
        source_node: str,
        source_role: NodeRole,
        target_message: str,
        content: str,
        critique_type: str = "LOGICAL",
        severity: float = 0.5,
        thread_id: Optional[str] = None,
    ) -> "DCPMessage":
        return cls(
            source_node=source_node,
            source_role=source_role.value,
            message_type=MessageType.CRITIQUE.value,
            thread_id=thread_id or str(uuid.uuid4()),
            in_reply_to=target_message,
            priority=min(0.95, 0.6 + severity * 0.3),
            payload={
                "target_message": target_message,
                "critique_type": critique_type,
                "content": content,
                "severity": severity,
                "counter_evidence": [],
                "suggested_modification": "",
            },
        )

    @classmethod
    def heartbeat(
        cls,
        source_node: str,
        status: NodeStatus = NodeStatus.HEALTHY,
        load: Optional[dict[str, float]] = None,
        active_threads: Optional[list[str]] = None,
    ) -> "DCPMessage":
        return cls(
            source_node=source_node,
            source_role=NodeRole.SATELLITE.value,
            message_type=MessageType.HEARTBEAT.value,
            priority=0.2,
            ttl=60,
            payload={
                "node_status": status.value,
                "load_metrics": load or {"cpu": 0.0, "memory": 0.0, "queue_depth": 0},
                "active_threads": active_threads or [],
                "last_sync": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            },
        )

    @classmethod
    def alert(
        cls,
        source_node: str,
        alert_type: AlertType,
        description: str,
        severity: float = 0.8,
        affected_nodes: Optional[list[str]] = None,
    ) -> "DCPMessage":
        return cls(
            source_node=source_node,
            source_role=NodeRole.WATCHER.value,
            message_type=MessageType.ALERT.value,
            priority=min(0.99, 0.7 + severity * 0.25),
            ttl=0,
            payload={
                "alert_type": alert_type.value,
                "severity": severity,
                "description": description,
                "affected_nodes": affected_nodes or [],
                "recommended_action": "",
            },
        )


class FilesystemBus:
    """Local-first transport: messages as files in a shared directory."""

    def __init__(self, bus_dir: str | Path = "/tmp/drift_hive/bus") -> None:
        self.bus_dir = Path(bus_dir)
        self.bus_dir.mkdir(parents=True, exist_ok=True)
        self._seen: set[str] = set()

    def send(self, msg: DCPMessage) -> None:
        path = self.bus_dir / f"{time.time_ns()}_{msg.message_id}.dcp"
        path.write_text(msg.to_json(), encoding="utf-8")

    def poll(self, max_age_seconds: float = 10.0) -> list[DCPMessage]:
        now = time.time()
        messages: list[DCPMessage] = []
        for path in sorted(self.bus_dir.glob("*.dcp")):
            try:
                age = now - path.stat().st_mtime
                if age > max_age_seconds:
                    path.unlink(missing_ok=True)
                    continue
                msg = DCPMessage.from_json(path.read_text(encoding="utf-8"))
                if msg.message_id not in self._seen:
                    self._seen.add(msg.message_id)
                    messages.append(msg)
            except Exception:
                continue
        # Prevent unbounded memory growth of _seen
        if len(self._seen) > 10_000:
            self._seen.clear()
        return messages

    def cleanup(self, max_age_seconds: float = 60.0) -> int:
        now = time.time()
        removed = 0
        for path in self.bus_dir.glob("*.dcp"):
            if now - path.stat().st_mtime > max_age_seconds:
                path.unlink(missing_ok=True)
                removed += 1
        return removed
