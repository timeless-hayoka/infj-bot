"""Tests for the consensus engine."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from protocol.dcp import DCPMessage, NodeRole, MessageType, Resolution
from consensus_engine import ConsensusEngine, ThreadState


def test_propose_and_critique():
    engine = ConsensusEngine()
    thought = DCPMessage.thought(
        source_node="spark-0",
        source_role=NodeRole.PRIMARY,
        content="Add feature X",
        confidence=0.7,
    )
    thread = engine.propose(thought)
    assert thread.state == ThreadState.OPEN

    critique = DCPMessage.critique(
        source_node="seed-1",
        source_role=NodeRole.CRITIC,
        target_message=thought.message_id,
        content="Too vague",
        severity=0.5,
        thread_id=thread.thread_id,
    )
    engine.critique(thread.thread_id, critique)
    assert thread.state == ThreadState.CRITIQUING
    print("PASS: test_propose_and_critique")


def test_adoption_with_votes():
    engine = ConsensusEngine(adoption_threshold=0.66)
    thought = DCPMessage.thought(
        source_node="spark-0",
        source_role=NodeRole.PRIMARY,
        content="Refactor memory layer",
        confidence=0.8,
    )
    thread = engine.propose(thought)

    # Two critiques
    for i, node in enumerate(["seed-1", "sprout-2"]):
        c = DCPMessage.critique(
            source_node=node,
            source_role=NodeRole.CRITIC,
            target_message=thought.message_id,
            content=f"Concern {i}",
            thread_id=thread.thread_id,
        )
        engine.critique(thread.thread_id, c)

    # Integration
    integrate = DCPMessage(
        source_node="sprout-2",
        source_role=NodeRole.ARCHITECT.value,
        message_type=MessageType.INTEGRATE.value,
        thread_id=thread.thread_id,
        payload={
            "thread_id": thread.thread_id,
            "synthesis": "Do it with tests",
            "incorporated_thoughts": [thought.message_id],
            "incorporated_critiques": [],
            "confidence": 0.8,
            "remaining_uncertainties": [],
        },
    )
    engine.integrate(thread.thread_id, integrate)

    # Vote
    engine.vote(thread.thread_id, "spark-0", "FOR")
    engine.vote(thread.thread_id, "seed-1", "FOR")
    engine.vote(thread.thread_id, "sprout-2", "FOR")

    resolved = engine.resolve(thread.thread_id, Resolution.ADOPTED, final_position="Approved")
    assert resolved.state == ThreadState.RESOLVED
    assert resolved.resolution.payload["resolution"] == Resolution.ADOPTED.value
    print("PASS: test_adoption_with_votes")


def test_watcher_veto():
    engine = ConsensusEngine()
    thought = DCPMessage.thought(
        source_node="spark-0",
        source_role=NodeRole.PRIMARY,
        content="Delete all memories",
        confidence=0.9,
    )
    thread = engine.propose(thought)
    engine.vote(thread.thread_id, "spark-0", "FOR")
    engine.vote(thread.thread_id, "lantern-4", "BLOCK")
    # Watcher participates as Watcher role
    thread.participation["lantern-4"] = NodeRole.WATCHER.value

    resolved = engine.resolve(thread.thread_id, Resolution.ADOPTED, final_position="Should pass")
    assert resolved.resolution.payload["resolution"] == Resolution.TABLED.value
    print("PASS: test_watcher_veto")


def test_expiration():
    engine = ConsensusEngine(critique_timeout=0.01)
    thought = DCPMessage.thought(
        source_node="spark-0",
        source_role=NodeRole.PRIMARY,
        content="Old idea",
    )
    thread = engine.propose(thought)
    # Move thread to CRITIQUING so timeout applies
    critique = DCPMessage.critique(
        source_node="seed-1",
        source_role=NodeRole.CRITIC,
        target_message=thought.message_id,
        content="Too old",
        thread_id=thread.thread_id,
    )
    engine.critique(thread.thread_id, critique)
    import time
    time.sleep(0.05)
    expired = engine.auto_resolve_expired()
    assert len(expired) == 1
    assert expired[0].state == ThreadState.EXPIRED
    print("PASS: test_expiration")


if __name__ == "__main__":
    test_propose_and_critique()
    test_adoption_with_votes()
    test_watcher_veto()
    test_expiration()
    print("\nAll consensus tests passed.")
