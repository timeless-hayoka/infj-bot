"""Node identity within the DRIFT Hive — self-model, capabilities, and state."""
from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Optional

from protocol.dcp import NodeRole, NodeStatus


@dataclass
class NodeCapabilities:
    can_reason: bool = True
    can_critique: bool = True
    can_remember: bool = True
    can_modify_self: bool = False
    can_use_tools: bool = False
    can_speak_human: bool = True
    max_context_tokens: int = 8192
    specialties: list[str] = field(default_factory=list)


@dataclass
class NodeIdentity:
    node_id: str
    role: NodeRole
    display_name: str = ""
    version: str = "1.0.0"
    capabilities: NodeCapabilities = field(default_factory=NodeCapabilities)
    status: NodeStatus = NodeStatus.HEALTHY
    joined_at: float = field(default_factory=time.time)
    last_heartbeat: float = field(default_factory=time.time)
    total_messages_sent: int = 0
    total_messages_received: int = 0
    active_threads: list[str] = field(default_factory=list)
    homeostasis_snapshot: dict[str, float] = field(default_factory=dict)
    shadow_snapshot: dict[str, Any] = field(default_factory=dict)
    growth_stage: str = "spark"
    public_key: Optional[str] = None

    def __post_init__(self):
        if not self.display_name:
            self.display_name = f"{self.role.value.title()}-{self.node_id.split('-')[-1]}"

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["role"] = self.role.value
        d["status"] = self.status.value
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), default=str, indent=2)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "NodeIdentity":
        d = dict(d)
        d["role"] = NodeRole(d.get("role", "satellite"))
        d["status"] = NodeStatus(d.get("status", "HEALTHY"))
        d["capabilities"] = NodeCapabilities(**d.get("capabilities", {}))
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})

    def is_healthy(self) -> bool:
        return self.status in (NodeStatus.HEALTHY, NodeStatus.RECOVERING)

    def is_quarantined(self) -> bool:
        return self.status == NodeStatus.QUARANTINED

    def seconds_since_heartbeat(self) -> float:
        return time.time() - self.last_heartbeat


class NodeRegistry:
    """Keeps track of all nodes in the hive."""

    def __init__(self, state_file: str = "hive_mind/nodes.json") -> None:
        self.state_file = Path(state_file)
        self._nodes: dict[str, NodeIdentity] = {}
        self._load()

    def _load(self) -> None:
        if self.state_file.exists():
            try:
                data = json.loads(self.state_file.read_text(encoding="utf-8"))
                for nid, ndict in data.get("nodes", {}).items():
                    self._nodes[nid] = NodeIdentity.from_dict(ndict)
            except Exception:
                pass

    def save(self) -> None:
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "saved_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "nodes": {nid: n.to_dict() for nid, n in self._nodes.items()},
        }
        self.state_file.write_text(json.dumps(payload, default=str, indent=2), encoding="utf-8")

    def register(self, node: NodeIdentity) -> None:
        self._nodes[node.node_id] = node
        self.save()

    def unregister(self, node_id: str) -> None:
        self._nodes.pop(node_id, None)
        self.save()

    def get(self, node_id: str) -> Optional[NodeIdentity]:
        return self._nodes.get(node_id)

    def all_nodes(self) -> list[NodeIdentity]:
        return list(self._nodes.values())

    def by_role(self, role: NodeRole) -> list[NodeIdentity]:
        return [n for n in self._nodes.values() if n.role == role]

    def healthy_nodes(self) -> list[NodeIdentity]:
        return [n for n in self._nodes.values() if n.is_healthy()]

    def update_heartbeat(self, node_id: str) -> None:
        node = self._nodes.get(node_id)
        if node:
            node.last_heartbeat = time.time()
            if node.status in (NodeStatus.DEGRADED, NodeStatus.OFFLINE):
                node.status = NodeStatus.RECOVERING
            self.save()

    def mark_degraded(self, node_id: str) -> None:
        node = self._nodes.get(node_id)
        if node and node.status != NodeStatus.QUARANTINED:
            node.status = NodeStatus.DEGRADED
            self.save()

    def mark_offline(self, node_id: str) -> None:
        node = self._nodes.get(node_id)
        if node:
            node.status = NodeStatus.OFFLINE
            self.save()

    def quarantine(self, node_id: str, reason: str = "") -> None:
        node = self._nodes.get(node_id)
        if node:
            node.status = NodeStatus.QUARANTINED
            # Log reason somewhere
            self.save()

    def stats(self) -> dict[str, Any]:
        return {
            "total": len(self._nodes),
            "healthy": sum(1 for n in self._nodes.values() if n.is_healthy()),
            "by_role": {
                role.value: len(self.by_role(role))
                for role in NodeRole
            },
            "by_status": {
                status.value: sum(1 for n in self._nodes.values() if n.status == status)
                for status in NodeStatus
            },
        }
