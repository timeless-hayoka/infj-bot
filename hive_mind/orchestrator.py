"""HiveOrchestrator — node registry and heartbeat for the Hive Mind."""

from typing import ClassVar


class HiveOrchestrator:
    """Manages the set of Hive nodes and their health status."""

    _DEFAULT_NODES: ClassVar = ["spark-0", "seed-1", "sprout-2", "lantern-4"]

    def __init__(self, nodes: list[str] | None = None):
        self._nodes: list[str] = list(nodes or self._DEFAULT_NODES)
        self._node_status: dict[str, str] = {n: "active" for n in self._nodes}

    def get_status(self) -> dict:
        active = [n for n, s in self._node_status.items() if s == "active"]
        return {
            "node_count": len(self._nodes),
            "active_node_count": len(active),
            "nodes": self._nodes,
            "node_status": dict(self._node_status),
            "status": "online" if active else "offline",
        }

    def register_node(self, node_id: str) -> None:
        if node_id not in self._nodes:
            self._nodes.append(node_id)
        self._node_status[node_id] = "active"

    def deregister_node(self, node_id: str) -> None:
        self._node_status[node_id] = "inactive"
