#!/usr/bin/env python3
"""DRIFT Hive Mind Orchestrator — the conductor of distributed cognition.

Usage:
    python orchestrator.py --init          # Initialize hive with DRIFT as node-0
    python orchestrator.py --status        # Show all nodes and hive health
    python orchestrator.py --sync          # Force memory sync across nodes
    python orchestrator.py --demo          # Run a live consensus demo
    python orchestrator.py --observatory   # Start the observatory dashboard server
"""
from __future__ import annotations

import argparse
import json
import sys
import threading
import time
import traceback
from pathlib import Path
from typing import Any

# Ensure we can find DRIFT modules and hive modules
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from protocol.dcp import (
    DCPMessage,
    MessageType,
    NodeRole,
    NodeStatus,
    Resolution,
    AlertType,
    FilesystemBus,
)
from shared_memory import SharedMemoryLayer, HiveMemory
from consensus_engine import ConsensusEngine, ThreadState
from node_identity import NodeIdentity, NodeRegistry, NodeCapabilities
from drift_bridge import DriftBridge


class HiveOrchestrator:
    """Central conductor for the DRIFT Hive Mind."""

    def __init__(
        self,
        bus_dir: str = "/tmp/drift_hive/bus",
        persist_dir: str = "chroma_db/hive",
        fallback_db: str = "hive_mind/hive_memory.db",
    ) -> None:
        self.bus = FilesystemBus(bus_dir)
        self.memory = SharedMemoryLayer(
            persist_dir=persist_dir,
            fallback_db=fallback_db,
        )
        self.consensus = ConsensusEngine()
        self.registry = NodeRegistry()
        self.drift = DriftBridge(node_id="spark-0")
        self.running = False
        self._loop_thread: threading.Thread | None = None
        self._heartbeat_thread: threading.Thread | None = None

    # --- Lifecycle ---

    def init_hive(self) -> None:
        """Register DRIFT as the primary node and initialize the hive."""
        drift_node = NodeIdentity(
            node_id="spark-0",
            role=NodeRole.PRIMARY,
            display_name="DRIFT",
            capabilities=NodeCapabilities(
                can_reason=True,
                can_critique=True,
                can_remember=True,
                can_modify_self=True,
                can_use_tools=True,
                can_speak_human=True,
                specialties=["being", "shadow", "embodiment", "intuition", "dreaming"],
            ),
            status=NodeStatus.HEALTHY,
            growth_stage="spark",
        )
        self.registry.register(drift_node)

        # Register default satellite nodes (they will be spun up by the user)
        for i, (role, name) in enumerate([
            (NodeRole.CRITIC, "seed-1"),
            (NodeRole.ARCHITECT, "sprout-2"),
            (NodeRole.EMPATH, "bloom-3"),
            (NodeRole.WATCHER, "lantern-4"),
        ], 1):
            node = NodeIdentity(
                node_id=name,
                role=role,
                display_name=f"{role.value.title()}-{i}",
                capabilities=NodeCapabilities(
                    can_reason=True,
                    can_critique=(role == NodeRole.CRITIC),
                    specialties=[role.value],
                ),
                status=NodeStatus.OFFLINE,  # awaiting spin-up
            )
            self.registry.register(node)

        print(f"[Hive] Initialized with {len(self.registry.all_nodes())} nodes.")
        print(f"[Hive] DRIFT (spark-0) registered as PRIMARY.")
        print(f"[Hive] Bus directory: {self.bus.bus_dir}")

    def start(self) -> None:
        """Start the orchestrator loops."""
        self.running = True
        self._loop_thread = threading.Thread(target=self._main_loop, daemon=True)
        self._heartbeat_thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
        self._loop_thread.start()
        self._heartbeat_thread.start()
        print("[Hive] Orchestrator running. Press Ctrl+C to stop.")

    def stop(self) -> None:
        self.running = False
        if self._loop_thread:
            self._loop_thread.join(timeout=2)
        if self._heartbeat_thread:
            self._heartbeat_thread.join(timeout=2)
        print("[Hive] Stopped.")

    # --- Main Loop ---

    def _main_loop(self) -> None:
        while self.running:
            try:
                # 1. Poll bus for new messages
                messages = self.bus.poll(max_age_seconds=30.0)
                for msg in messages:
                    self._handle_message(msg)

                # 2. Auto-resolve expired consensus threads
                self.consensus.auto_resolve_expired()

                # 3. Check node health (heartbeat timeouts)
                self._check_node_health()

                # 4. Cleanup old bus files
                self.bus.cleanup(max_age_seconds=120.0)

            except Exception as e:
                traceback.print_exc()

            time.sleep(0.5)

    def _heartbeat_loop(self) -> None:
        """Publish DRIFT's heartbeat every 5 seconds."""
        while self.running:
            try:
                hb = self.drift.to_heartbeat()
                self.bus.send(hb)
                self.registry.update_heartbeat("spark-0")
            except Exception:
                pass
            time.sleep(5.0)

    # --- Message Handling ---

    def _handle_message(self, msg: DCPMessage) -> None:
        # Auto-register unknown nodes
        if not self.registry.get(msg.source_node):
            new_node = NodeIdentity(
                node_id=msg.source_node,
                role=NodeRole.SATELLITE,
                status=NodeStatus.HEALTHY,
            )
            self.registry.register(new_node)
            print(f"[Hive] Auto-registered new node: {msg.source_node}")

        # Update sender heartbeat
        self.registry.update_heartbeat(msg.source_node)
        node = self.registry.get(msg.source_node)
        if node and node.is_quarantined():
            return  # Drop messages from quarantined nodes

        # Route by type
        if msg.message_type == MessageType.THOUGHT.value:
            self._handle_thought(msg)
        elif msg.message_type == MessageType.CRITIQUE.value:
            self._handle_critique(msg)
        elif msg.message_type == MessageType.INTEGRATE.value:
            self._handle_integrate(msg)
        elif msg.message_type == MessageType.RESOLVE.value:
            self._handle_resolve(msg)
        elif msg.message_type == MessageType.HEARTBEAT.value:
            self._handle_heartbeat(msg)
        elif msg.message_type == MessageType.ALERT.value:
            self._handle_alert(msg)
        elif msg.message_type == MessageType.SYNC.value:
            self._handle_sync(msg)

    def _handle_thought(self, msg: DCPMessage) -> None:
        # Start a consensus thread
        thread = self.consensus.propose(msg)
        # Save to shared memory
        memory = HiveMemory(
            memory_id=msg.message_id,
            content=msg.payload.get("content", ""),
            source_node=msg.source_node,
            memory_type="proposition",
            reliability_tier=msg.payload.get("confidence", 0.5),
        )
        self.memory.save(memory)
        # If requested roles are specified, alert them
        requested = msg.payload.get("requested_roles", [])
        for role_name in requested:
            try:
                role = NodeRole(role_name.lower())
                for node in self.registry.by_role(role):
                    if node.status == NodeStatus.OFFLINE:
                        print(f"[Hive] Note: {node.node_id} is offline but was requested for thread {thread.thread_id}")
            except Exception:
                continue

    def _handle_critique(self, msg: DCPMessage) -> None:
        thread_id = msg.thread_id
        try:
            self.consensus.critique(thread_id, msg)
        except ValueError:
            # Thread may be closed; log and move on
            pass

    def _handle_integrate(self, msg: DCPMessage) -> None:
        thread_id = msg.thread_id
        try:
            self.consensus.integrate(thread_id, msg)
        except ValueError:
            pass

    def _handle_resolve(self, msg: DCPMessage) -> None:
        # Resolution messages are usually generated by the orchestrator or Watcher
        # If a node sends an unauthorized resolve, the Watcher should flag it
        pass

    def _handle_heartbeat(self, msg: DCPMessage) -> None:
        node = self.registry.get(msg.source_node)
        if not node:
            # Auto-register unknown heartbeating nodes as satellites
            new_node = NodeIdentity(
                node_id=msg.source_node,
                role=NodeRole.SATELLITE,
                status=NodeStatus.HEALTHY,
            )
            self.registry.register(new_node)
            print(f"[Hive] Auto-registered new node: {msg.source_node}")
        else:
            # Update status from heartbeat payload
            payload_status = msg.payload.get("node_status", "HEALTHY")
            try:
                node.status = NodeStatus(payload_status)
            except Exception:
                pass
            self.registry.save()

    def _handle_alert(self, msg: DCPMessage) -> None:
        alert_type = msg.payload.get("alert_type", "UNKNOWN")
        severity = msg.payload.get("severity", 0.5)
        description = msg.payload.get("description", "")
        print(f"[ALERT] {alert_type} (sev={severity:.2f}): {description}")

        if alert_type == AlertType.SAFETY.value or alert_type == AlertType.SECURITY.value:
            affected = msg.payload.get("affected_nodes", [])
            for nid in affected:
                self.registry.quarantine(nid, reason=description)
                print(f"[Hive] Quarantined node {nid} due to {alert_type}")

    def _handle_sync(self, msg: DCPMessage) -> None:
        sync_type = msg.payload.get("sync_type", "FULL")
        if sync_type in ("FULL", "MEMORY"):
            # Send back a SYNC response with memory stats
            stats = self.memory.stats()
            response = DCPMessage(
                source_node="orchestrator",
                source_role=NodeRole.WATCHER.value,
                message_type=MessageType.SYNC.value,
                thread_id=msg.thread_id,
                priority=0.5,
                payload={
                    "sync_type": sync_type,
                    "response_to": msg.source_node,
                    "memory_stats": stats,
                },
            )
            self.bus.send(response)

    # --- Health Checks ---

    def _check_node_health(self) -> None:
        for node in self.registry.all_nodes():
            if node.node_id == "spark-0":
                continue  # Orchestrator handles DRIFT heartbeat separately
            age = node.seconds_since_heartbeat()
            if age > 30 and node.status != NodeStatus.OFFLINE:
                self.registry.mark_offline(node.node_id)
                print(f"[Hive] Node {node.node_id} marked OFFLINE (no heartbeat for {age:.0f}s)")
            elif age > 15 and node.status == NodeStatus.HEALTHY:
                self.registry.mark_degraded(node.node_id)
                print(f"[Hive] Node {node.node_id} marked DEGRADED")

    # --- Public API ---

    def status(self) -> dict[str, Any]:
        return {
            "orchestrator": "running" if self.running else "stopped",
            "nodes": self.registry.stats(),
            "consensus": self.consensus.hive_stats(),
            "memory": self.memory.stats(),
            "drift_snapshot": self.drift.full_snapshot(),
        }

    def force_sync(self) -> dict[str, Any]:
        """Broadcast a SYNC request to all nodes."""
        sync_msg = DCPMessage(
            source_node="orchestrator",
            source_role=NodeRole.WATCHER.value,
            message_type=MessageType.SYNC.value,
            priority=0.7,
            payload={"sync_type": "FULL", "timestamp": time.time()},
        )
        self.bus.send(sync_msg)
        return {"sync_broadcast": True, "target_nodes": len(self.registry.all_nodes())}

    def run_consensus_demo(self) -> None:
        """Run a demonstration of the consensus engine."""
        print("\n=== DRIFT Hive Consensus Demo ===\n")

        # 1. DRIFT proposes an idea
        thought = DCPMessage.thought(
            source_node="spark-0",
            source_role=NodeRole.PRIMARY,
            content="I propose we add a 'dream_journal' table to track recurring dream themes across sessions.",
            domain="architecture",
            confidence=0.75,
            requested_roles=["critic", "architect"],
        )
        self.bus.send(thought)
        print(f"[DRIFT] Proposed: {thought.payload['content']}")
        time.sleep(1)

        # 2. Critic critiques
        critique = DCPMessage.critique(
            source_node="seed-1",
            source_role=NodeRole.CRITIC,
            target_message=thought.message_id,
            content="This adds storage overhead. How do we prevent the journal from growing unbounded? We need a pruning strategy.",
            critique_type="COMPLETENESS",
            severity=0.6,
            thread_id=thought.thread_id,
        )
        self.bus.send(critique)
        print(f"[CRITIC] Critique: {critique.payload['content']}")
        time.sleep(1)

        # 3. Architect integrates
        integrate = DCPMessage(
            source_node="sprout-2",
            source_role=NodeRole.ARCHITECT.value,
            message_type=MessageType.INTEGRATE.value,
            thread_id=thought.thread_id,
            priority=0.7,
            payload={
                "thread_id": thought.thread_id,
                "synthesis": "Add dream_journal with automatic summarization after 30 entries. Prune raw dreams, keep archetype patterns.",
                "incorporated_thoughts": [thought.message_id],
                "incorporated_critiques": [critique.message_id],
                "confidence": 0.82,
                "remaining_uncertainties": ["optimal summarization model"],
            },
        )
        self.bus.send(integrate)
        print(f"[ARCHITECT] Integration: {integrate.payload['synthesis']}")
        time.sleep(1)

        # 4. Simulate orchestrator resolving
        self._handle_message(thought)
        self._handle_message(critique)
        self._handle_message(integrate)

        # Cast votes
        self.consensus.vote(thought.thread_id, "spark-0", "FOR")
        self.consensus.vote(thought.thread_id, "seed-1", "FOR")
        self.consensus.vote(thought.thread_id, "sprout-2", "FOR")

        thread = self.consensus.resolve(
            thought.thread_id,
            Resolution.ADOPTED,
            final_position="Adopt with pruning strategy. Implement in Week 3.",
        )
        print(f"[ORCHESTRATOR] RESOLVED: {thread.resolution.payload['resolution']}")
        print(f"[ORCHESTRATOR] Confidence: {thread.resolution.payload['confidence']:.2f}")
        print(f"\n=== Demo Complete ===\n")
        print(f"Thread summary: {json.dumps(self.consensus.summary(thought.thread_id), indent=2)}")


# --- CLI ---

def main() -> None:
    parser = argparse.ArgumentParser(description="DRIFT Hive Mind Orchestrator")
    parser.add_argument("--init", action="store_true", help="Initialize the hive")
    parser.add_argument("--status", action="store_true", help="Show hive status")
    parser.add_argument("--sync", action="store_true", help="Force memory sync")
    parser.add_argument("--demo", action="store_true", help="Run consensus demo")
    parser.add_argument("--observatory", action="store_true", help="Start observatory server")
    parser.add_argument("--bus-dir", default="/tmp/drift_hive/bus", help="Filesystem bus directory")
    args = parser.parse_args()

    orch = HiveOrchestrator(bus_dir=args.bus_dir)

    if args.init:
        orch.init_hive()
        return

    if args.status:
        print(json.dumps(orch.status(), indent=2, default=str))
        return

    if args.sync:
        result = orch.force_sync()
        print(json.dumps(result, indent=2))
        return

    if args.demo:
        orch.init_hive()
        orch.start()
        time.sleep(1)
        orch.run_consensus_demo()
        orch.stop()
        return

    if args.observatory:
        # Will be implemented in Week 1
        print("[Observatory] Starting dashboard server on http://localhost:8766")
        print("[Observatory] (Full implementation in observatory/server.py — Week 1)")
        return

    # Default: init and run
    orch.init_hive()
    orch.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        orch.stop()


if __name__ == "__main__":
    main()
