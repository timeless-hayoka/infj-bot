"""Tests for the shared memory layer."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import tempfile

from shared_memory import SharedMemoryLayer, HiveMemory


def test_save_and_retrieve():
    with tempfile.TemporaryDirectory() as tmpdir:
        mem = SharedMemoryLayer(
            persist_dir=f"{tmpdir}/chroma",
            fallback_db=f"{tmpdir}/mem.db",
        )
        m = HiveMemory(
            memory_id="test-1",
            content="DRIFT is learning to dream",
            source_node="spark-0",
            memory_type="semantic",
            reliability_tier=0.8,
            consensus_score=0.3,
        )
        mem.save(m)
        results = mem.retrieve(query_text="dream", top_k=5)
        assert len(results) >= 1
        assert results[0].memory_id == "test-1"
        print("PASS: test_save_and_retrieve")


def test_validate_boosts_consensus():
    with tempfile.TemporaryDirectory() as tmpdir:
        mem = SharedMemoryLayer(
            fallback_db=f"{tmpdir}/mem.db",
        )
        m = HiveMemory(
            memory_id="test-2",
            content="Shadow work is essential",
            source_node="spark-0",
        )
        mem.save(m)
        mem.validate("test-2", "seed-1", boost=0.15)
        mem.validate("test-2", "sprout-2", boost=0.15)
        results = mem.retrieve(query_text="shadow", top_k=5)
        assert results[0].consensus_score > 0.25
        print("PASS: test_validate_boosts_consensus")


def test_stats():
    with tempfile.TemporaryDirectory() as tmpdir:
        mem = SharedMemoryLayer(
            fallback_db=f"{tmpdir}/mem.db",
        )
        for i in range(3):
            mem.save(HiveMemory(
                memory_id=f"s-{i}",
                content=f"Memory {i}",
                source_node="spark-0" if i < 2 else "seed-1",
            ))
        stats = mem.stats()
        assert stats["total_memories"] == 3
        assert stats["by_node"]["spark-0"] == 2
        print("PASS: test_stats")


if __name__ == "__main__":
    test_save_and_retrieve()
    test_validate_boosts_consensus()
    test_stats()
    print("\nAll shared memory tests passed.")
