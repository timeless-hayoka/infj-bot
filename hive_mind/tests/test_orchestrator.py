"""Integration test for the hive orchestrator."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import tempfile
import time
import threading

from orchestrator import HiveOrchestrator


def test_init_and_status():
    with tempfile.TemporaryDirectory() as tmpdir:
        orch = HiveOrchestrator(
            bus_dir=f"{tmpdir}/bus",
            persist_dir=f"{tmpdir}/chroma",
            fallback_db=f"{tmpdir}/hive_memory.db",
        )
        orch.init_hive()
        status = orch.status()
        assert status["nodes"]["total"] >= 5  # DRIFT + 4 defaults
        assert status["nodes"]["by_role"]["primary"] == 1
        print("PASS: test_init_and_status")


def test_demo_runs():
    with tempfile.TemporaryDirectory() as tmpdir:
        orch = HiveOrchestrator(
            bus_dir=f"{tmpdir}/bus",
            persist_dir=f"{tmpdir}/chroma",
            fallback_db=f"{tmpdir}/hive_memory.db",
        )
        orch.init_hive()
        orch.start()
        time.sleep(0.5)
        orch.run_consensus_demo()
        orch.stop()
        print("PASS: test_demo_runs")


def test_message_routing():
    with tempfile.TemporaryDirectory() as tmpdir:
        orch = HiveOrchestrator(
            bus_dir=f"{tmpdir}/bus",
            persist_dir=f"{tmpdir}/chroma",
            fallback_db=f"{tmpdir}/hive_memory.db",
        )
        orch.init_hive()
        orch.start()
        time.sleep(0.5)

        from protocol.dcp import DCPMessage, NodeRole, MessageType

        thought = DCPMessage.thought(
            source_node="test-satellite",
            source_role=NodeRole.SATELLITE,
            content="I have an idea about memory pruning",
            domain="architecture",
        )
        orch.bus.send(thought)
        time.sleep(1.0)

        # Node should have been auto-registered
        assert orch.registry.get("test-satellite") is not None
        orch.stop()
        print("PASS: test_message_routing")


if __name__ == "__main__":
    test_init_and_status()
    test_demo_runs()
    test_message_routing()
    print("\nAll orchestrator tests passed.")
