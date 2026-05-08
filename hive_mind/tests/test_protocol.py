"""Tests for DCP message creation, serialization, and bus transport."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import json
import time
import tempfile

from protocol.dcp import (
    DCPMessage,
    MessageType,
    NodeRole,
    NodeStatus,
    AlertType,
    FilesystemBus,
)


def test_message_creation():
    msg = DCPMessage.thought(
        source_node="spark-0",
        source_role=NodeRole.PRIMARY,
        content="Test thought",
        confidence=0.9,
    )
    assert msg.message_type == MessageType.THOUGHT.value
    assert msg.source_node == "spark-0"
    assert msg.payload["confidence"] == 0.9
    print("PASS: test_message_creation")


def test_roundtrip():
    msg = DCPMessage.critique(
        source_node="seed-1",
        source_role=NodeRole.CRITIC,
        target_message="abc-123",
        content="This is wrong",
        severity=0.7,
    )
    json_str = msg.to_json()
    restored = DCPMessage.from_json(json_str)
    assert restored.message_id == msg.message_id
    assert restored.payload["severity"] == 0.7
    print("PASS: test_roundtrip")


def test_bus_transport():
    with tempfile.TemporaryDirectory() as tmpdir:
        bus = FilesystemBus(tmpdir)
        msg = DCPMessage.heartbeat(
            source_node="test-node",
            status=NodeStatus.HEALTHY,
            load={"cpu": 0.3, "memory": 0.4, "queue_depth": 0},
        )
        bus.send(msg)
        time.sleep(0.2)
        polled = bus.poll(max_age_seconds=10)
        assert len(polled) == 1
        assert polled[0].source_node == "test-node"
        print("PASS: test_bus_transport")


def test_bus_deduplication():
    with tempfile.TemporaryDirectory() as tmpdir:
        bus = FilesystemBus(tmpdir)
        msg = DCPMessage.heartbeat(source_node="dup-node")
        bus.send(msg)
        time.sleep(0.1)
        _ = bus.poll(max_age_seconds=10)
        polled2 = bus.poll(max_age_seconds=10)
        assert len(polled2) == 0  # deduplicated
        print("PASS: test_bus_deduplication")


def test_alert_priority():
    alert = DCPMessage.alert(
        source_node="lantern-4",
        alert_type=AlertType.SAFETY,
        description="Suspicious tool use detected",
        severity=0.95,
    )
    assert alert.priority > 0.9
    print("PASS: test_alert_priority")


if __name__ == "__main__":
    test_message_creation()
    test_roundtrip()
    test_bus_transport()
    test_bus_deduplication()
    test_alert_priority()
    print("\nAll protocol tests passed.")
